from __future__ import with_statement

import ConfigParser
import logging
import os
import pkg_resources
import pickle
import shutil
import sys
import tempfile
import threading
import transaction

from persistent.mapping import PersistentMapping

from pyramid.config import Configurator
from pyramid.util import DottedNameResolver
from repoze.depinj import lookup
from repoze.retry import Retry
from repoze.tm import TM as make_tm
from repoze.urchin import UrchinMiddleware
from repoze.who.config import WhoConfig
from repoze.who.plugins.zodb.users import Users
from repoze.who.middleware import PluggableAuthenticationMiddleware
from repoze.zodbconn.finder import PersistentApplicationFinder
from repoze.zodbconn.connector import make_app as zodb_connector
from repoze.zodbconn.uri import db_from_uri

from zope.component import queryUtility

from karlserve.log import set_subsystem
from karlserve.textindex import KarlPGTextIndex

import karl.includes
from karl.application import configure_karl as configure_default
from karl.bootstrap.interfaces import IBootstrapper
from karl.bootstrap.bootstrap import populate
from karl.errorlog import error_log_middleware
from karl.modeapps.maintenance import maintenance
from karl.models.site import get_weighted_textrepr
from karl.utils import asbool

try:
    from psycopg2.extensions import TransactionRollbackError
    from psycopg2 import IntegrityError
except ImportError:
    class TransactionRollbackError(Exception):
        pass
    class IntegrityError(Exception):
        pass
from repoze.retry import ConflictError
from repoze.retry import RetryException

retryable = (IntegrityError, TransactionRollbackError,
    ConflictError, RetryException,)


def get_instances(settings):
    instances = settings.get('instances')
    if instances is None:
        instances = lookup(Instances)(settings)
        settings['instances'] = instances
    return instances


class _InstanceProperty(object):
    """
    Descriptor for storing a property of an instance that can't be stored in
    the database for that instance. These properties are stored as pickles in
    var/instance/<instance_name>/<property_name> in the filesystem.
    """
    def __init__(self, name, default=None):
        self.name = name
        self.default = default
        self.type = type

    def _fname(self, instance):
        return os.path.join(instance.config['var_instance'], self.name)

    def __get__(self, instance, cls):
        fname = self._fname(instance)
        if not os.path.exists(fname):
            return self.default
        return pickle.load(open(fname))

    def __set__(self, instance, value):
        fname = self._fname(instance)
        if value == self.default:
            if os.path.exists(fname):
                os.remove(fname)
        else:
            folder = os.path.dirname(fname)
            if not os.path.exists(folder):
                os.makedirs(folder)
            with open(fname, 'w') as f:
                pickle.dump(value, f)


class Instances(object):
    root_instance = None

    def __init__(self, settings):
        self.settings = settings
        ini_file = settings['instances_config']
        here = os.path.dirname(os.path.abspath(ini_file))
        config = ConfigParser.ConfigParser(dict(here=here))
        config.read(ini_file)
        instances = {}
        virtual_hosts = {}
        for section in config.sections():
            if not section.startswith('instance:'):
                continue
            name = section[9:]
            options = {}
            for option in config.options(section):
                value = config.get(section, option)
                if option.endswith('keep_history'):
                    value = asbool(value)
                options[option] = value
            instances[name] = LazyInstance(name, settings, options)
            virtual_host = options.get('virtual_host')
            if virtual_host:
                for host in virtual_host.split():
                    host = host.strip()
                    virtual_hosts[host] = name
            if asbool(options.get('root', 'false')):
                self.root_instance = name

        self.instances = instances
        self.virtual_hosts = virtual_hosts

    def get(self, name):
        return self.instances.get(name)

    def get_virtual_host(self, host):
        return self.virtual_hosts.get(host)

    def get_names(self):
        return list(self.instances.keys())

    def close(self):
        for instance in self.instances.values():
            instance.close()


class LazyInstance(object):
    _instance = None
    _pipeline = None
    _tmp_folder = None

    last_sync_tid = _InstanceProperty('last_sync_tid')
    mode = _InstanceProperty('mode', default='NORMAL')

    def _make_instance_specific(self, config, key):
        if key not in config:
            return
        config[key] = os.path.join(config[key], self.name)

    def __init__(self, name, global_config, options):
        self.name = name

        self.config = config = global_config.copy()
        for setting, value in config.items():
            if setting.endswith('blob_cache'):
                config[setting] = os.path.join(value, name)
        self._make_instance_specific(config, 'var_instance')
        self._make_instance_specific(config, 'error_monitor_dir')
        config.update(options)
        config['read_only'] = self.mode == 'READONLY'

    def pipeline(self):
        pipeline = self._pipeline
        if pipeline is None:
            if self.mode == 'MAINTENANCE':
                pipeline = lookup(maintenance)(None)
            else:
                instance = self.instance()
                pipeline = lookup(make_karl_pipeline)(instance)
            self._pipeline = pipeline
        return pipeline

    def instance(self):
        instance = self._instance
        if instance is None:
            instance = self._spin_up()
            self._instance = instance
        return instance

    def close(self):
        instance = self._instance
        if instance is not None:
            instance.close()
            self._instance = None
        if self._tmp_folder is not None:
            shutil.rmtree(self._tmp_folder)
        self._tmp_folder = None

    @property
    def uri(self):
        uri = self.config.get('zodb_uri')
        if uri is None:
            config = self.config
            cache_size = 10000
            if 'zodb.cache_size' in config:
                cache_size = int(config['zodb.cache_size'])
            pool_size = 3
            if 'zodb.pool_size' in config:
                pool_size = int(config['zodb.pool_size'])
            uri = self._write_zconfig(
                'zodb.conf', config['dsn'], config['blob_cache'], cache_size,
                pool_size, config.get('keep_history', False),
                config['read_only'], config.get('relstorage.cache_servers'),
                config.get('relstorage.cache_prefix'),
            )
            self.config['zodb_uri'] = uri
        return uri

    @property
    def tmp(self):
        tmp = self._tmp_folder
        if tmp is None:
            var_tmp = self.config['var_tmp']
            if not os.path.exists(var_tmp):
                os.makedirs(var_tmp)
            self._tmp_folder = tmp = tempfile.mkdtemp(
                '.karlserve', dir=var_tmp)
        return tmp

    def _spin_up(self):
        config = self.config
        name = self.name

        # Write postoffice zodb config
        po_uri = config.get('postoffice.zodb_uri')
        if po_uri is None:
            if 'postoffice.dsn' in config:
                if 'postoffice.blob_cache' not in config:
                    raise ValueError("If postoffice.dsn is in config, then "
                                     "postoffice.blob_cache is required.")
                po_uri = self._write_zconfig(
                    'postoffice.conf', config['postoffice.dsn'],
                    config['postoffice.blob_cache'], name='postoffice')
                config['postoffice.zodb_uri'] = po_uri
        if po_uri:
            config['postoffice.queue'] = name

        pg_dsn = self.config.get('pgtextindex.dsn')
        if pg_dsn is None:
            pg_dsn = self.config.get('dsn')
        if pg_dsn is not None:
            config['pgtextindex.dsn'] = pg_dsn

        instance = lookup(make_karl_instance)(name, config, self.uri)
        self._instance = instance
        return instance

    def _write_zconfig(
            self, fname, dsn, blob_cache, cache_size=10000, pool_size=3,
            keep_history=False, read_only=False, cache_servers=None,
            cache_prefix=None, poll_interval=0, name=None):
        path = os.path.join(self.tmp, fname)
        uri = 'zconfig://%s' % path
        config = dict(
            dsn=dsn, blob_cache=blob_cache, cache_size=cache_size,
            pool_size=pool_size, keep_history=keep_history,
            read_only=read_only, name=name
        )
        if cache_servers:
            config['cache_servers'] = cache_servers
            config['poll_interval'] = poll_interval
            if cache_prefix is not None:
                config['cache_prefix'] = cache_prefix
            else:
                config['cache_prefix'] = self.name
            zconfig = zconfig_template_w_memcache % config
        else:
            zconfig = zconfig_template % config
        with open(path, 'w') as f:
            f.write(zconfig)
        return uri

    def __del__(self):
        if self._tmp_folder is not None:
            shutil.rmtree(self._tmp_folder)


def _get_config(global_config, uri):
    db = db_from_uri(uri)
    conn = db.open()
    root = conn.root()

    config = default_config.copy()
    config.update(global_config)
    instance_config = root.get('instance_config', None)
    if instance_config is None:
        instance_config = PersistentMapping(default_instance_config)
        root['instance_config'] = instance_config
    config.update(instance_config)
    if 'envelope_from_addr' not in config:
        config['envelope_from_addr'] = (
            'karl@%s' % config['system_email_domain'])

    transaction.commit()
    conn.close()
    db.close()
    del db, conn, root

    return config


def make_karl_instance(name, global_config, uri):
    settings = _get_config(global_config, uri)

    def appmaker(folder, name='site'):
        if name not in folder:
            bootstrapper = queryUtility(IBootstrapper, default=populate)
            bootstrapper(folder, name)

            # Use pgtextindex
            if 'pgtextindex.dsn' in settings:
                site = folder.get(name)
                index = lookup(KarlPGTextIndex)(get_weighted_textrepr)
                site.catalog['texts'] = index

            transaction.commit()

        return folder[name]

    # paster app settings callback
    uris = [uri]
    if 'postoffice.zodb_uri' in settings:
        po_uri = settings['postoffice.zodb_uri']
        if not po_uri.startswith('zconfig') and 'database_name=' not in po_uri:
            if '?' not in po_uri:
                po_uri += '?'
            else:
                po_uri += '&'
            po_uri += 'database_name=postoffice'
        uris.append(po_uri)

    finder = PersistentApplicationFinder(uris, appmaker)
    def get_root(request):
        return finder(request.environ)
    def closer():
        db = finder.db
        if db is not None:
            for database in db.databases.values():
                database.close()
            finder.db = None

    # Subsystem for logging
    set_subsystem('karl')

    # Make Pyramid app
    #
    # Do the configuration dance. If a 'package' setting is present, then
    # that package is the customization package and should be used to configure
    # the application.  Configuration can be done either by loading ZCML or by
    # calling a function for configuring Karl imperatively.  Imperative
    # configuration is preferred with loading of ZCML as a fallback.

    # Find package and configuration
    pkg_name = settings.get('package', None)
    configure_karl = None
    if pkg_name:
        __import__(pkg_name)
        package = sys.modules[pkg_name]
        configure_karl = get_imperative_config(package)
        if configure_karl is not None:
            filename = None
        else:
            filename = 'configure.zcml'
            # BBB Customization packages may be using ZCML style config but
            # need configuration done imperatively in core Karl.  These
            # customizaton packages have generally been written before the
            # introduction of imperative style config.
            configure_karl = configure_default
    else:
        package = karl.includes
        configure_karl = configure_default
        filename = None

    config = Configurator(package=package, settings=settings,
            root_factory=get_root, autocommit=True)
    config.begin()
    if filename is not None:
        if configure_karl is not None: # BBB See above
            configure_karl(config, load_zcml=False)
        config.hook_zca()
        config.include('pyramid_zcml')
        config.load_zcml(filename)
    else:
        configure_karl(config)
    config.end()

    app = config.make_wsgi_app()
    app.config = settings
    app.uris = uris
    app.close = closer

    return app


def get_imperative_config(package):
    resolver = DottedNameResolver(package)
    try:
        return resolver.resolve('.application:configure_karl')
    except ImportError:
        return None


def make_who_middleware(app, config):
    who_config = pkg_resources.resource_stream(__name__, 'who.ini').read()
    who_config = who_config % dict(
        cookie=config['who_cookie'],
        secret=config['who_secret'],
        realm=config.get('who_realm', config['system_name']))

    parser = WhoConfig(config['here'])
    parser.parse(who_config)

    return PluggableAuthenticationMiddleware(
        app,
        parser.identifiers,
        parser.authenticators,
        parser.challengers,
        parser.mdproviders,
        parser.request_classifier,
        parser.challenge_decider,
        None,  # log_stream
        logging.INFO,
        parser.remote_user_key,
    )


def make_karl_pipeline(app):
    config = app.config
    uris = app.uris
    pipeline = app
    urchin_account = config.get('urchin.account')
    if urchin_account:
        pipeline = UrchinMiddleware(pipeline, urchin_account)
    pipeline = make_who_middleware(pipeline, config)
    pipeline = make_tm(pipeline)
    print 'URIs', uris
    pipeline = zodb_connector(pipeline, config, zodb_uri=uris)
    pipeline = Retry(pipeline, 3, retryable)
    pipeline = error_log_middleware(pipeline)
    return pipeline


def find_users(root):
    # Called by repoze.who
    if not 'site' in root:
        return Users()
    return root['site'].users


_threadlocal = threading.local()


def set_current_instance(name):
    _threadlocal.instance = name


def get_current_instance():
    return _threadlocal.instance


default_instance_config = {
    'offline_app_url': 'karl.example.org',
    'system_name': 'KARL',
    'system_email_domain': 'example.org',
    'admin_email': 'admin@example.org',
    'error_monitor_subsystems': [
        'karl', 'mailin', 'mailout', 'digest', 'update_feeds']
}

# Hardwired for baby Karls
default_config = {
    'jquery_dev_mode': False,
    'debug': False,
    'reload_templates': False,
    'js_devel_mode': False,
    'static_postfix': '/static',
    'upload_limit': 0,  # XXX ???
    'min_pw_length': 8,
    'selectable_groups': 'group.KarlStaff group.KarlUserAdmin group.KarlAdmin '
                         'group.KarlCommunications',
    'aspell_executable': 'aspell',
    'aspell_max_words': 5000,
    'aspell_languages': 'en',
}

zconfig_template = """
%%import relstorage
<zodb>
  database-name %(name)s
  cache-size %(cache_size)s
  pool-size %(pool_size)s
  <relstorage>
    <postgresql>
      dsn %(dsn)s
    </postgresql>
    shared-blob-dir False
    blob-dir %(blob_cache)s
    blob-cache-size 1gb
    keep-history %(keep_history)s
    read-only %(read_only)s
  </relstorage>
</zodb>
"""

zconfig_template_w_memcache = """
%%import relstorage
<zodb>
  database-name %(name)s
  cache-size %(cache_size)s
  pool-size %(pool_size)s
  <relstorage>
    <postgresql>
      dsn %(dsn)s
    </postgresql>
    shared-blob-dir False
    blob-dir %(blob_cache)s
    blob-cache-size 1gb
    keep-history %(keep_history)s
    read-only %(read_only)s
    cache-servers %(cache_servers)s
    cache-prefix %(cache_prefix)s
    poll-interval %(poll_interval)s
  </relstorage>
</zodb>
"""
