from __future__ import with_statement

import ConfigParser
import logging
import os
import pkg_resources
import shutil
import sys
import tempfile
import threading
import transaction

from persistent.mapping import PersistentMapping

from repoze.bfg.router import make_app as bfg_make_app

from repoze.tm import make_tm
from repoze.zodbconn.finder import PersistentApplicationFinder
from repoze.zodbconn.connector import make_app as zodb_connector
from repoze.zodbconn.uri import db_from_uri
from repoze.who.config import WhoConfig
from repoze.who.plugins.zodb.users import Users
from repoze.who.middleware import PluggableAuthenticationMiddleware

from zope.component import queryUtility

from karlserve.log import configure_log
from karlserve.log import set_subsystem
from karlserve.textindex import KarlPGTextIndex

from karl.bootstrap.interfaces import IBootstrapper
from karl.bootstrap.bootstrap import populate
from karl.errorlog import error_log_middleware
from karl.errorpage import ErrorPageFilter
from karl.models.site import get_weighted_textrepr


def get_instances(settings):
    instances = settings.get('instances')
    if instances is None:
        instances = Instances(settings)
        settings['instances'] = instances
    return instances


class Instances(object):

    def __init__(self, settings):
        self.settings = settings
        ini_file = settings['instances_config']
        config = ConfigParser.ConfigParser()
        config.read(ini_file)
        instances = {}
        virtual_hosts = {}
        for section in config.sections():
            if not section.startswith('instance:'):
                continue
            name = section[9:]
            options = dict([(option, config.get(section, option)) for
                            option in config.options(section)])
            instances[name] = LazyInstance(name, settings, options)
            virtual_host = options.get('virtual_host')
            if virtual_host:
                virtual_hosts[virtual_host] = name
        self.instances = instances
        self.virtual_hosts = virtual_hosts

    def get(self, name):
        return self.instances.get(name)

    def get_virtual_host(self, host):
        return self.virtual_hosts.get(host)

    def get_names(self):
        return list(self.instances.keys())


class LazyInstance(object):
    _instance = None
    _pipeline = None
    _tmp_folder = None
    _uri = None

    def __init__(self, name, global_config, options):
        self.name = name
        self.global_config = global_config
        self.options = options

    def pipeline(self):
        pipeline = self._pipeline
        if pipeline is None:
            instance = self.instance()
            pipeline = make_karl_pipeline(
                instance, self.global_config, self._uri)
            self._pipeline = pipeline
        return pipeline

    def instance(self):
        instance = self._instance
        if instance is None:
            instance = self._spin_up()
            self._instance = instance
        return instance

    def _spin_up(self):
        config = self.global_config.copy()
        name = self.name

        # Create temp folder for zodb configuration files
        self._tmp_folder = tmp_folder = tempfile.mkdtemp('.karl')

        uri = self.options.get('zodb_uri')
        if uri is None:
            # Write main zodb config
            uri = self._write_zconfig(
                tmp_folder, 'zodb.conf', self.options['dsn'],
                config['blob_cache'])

        # Write postoffice zodb config
        po_uri = self.options.get('postoffice.zodb_uri')
        if po_uri is None:
            if 'postoffice.dsn' in config:
                if 'postoffice.blob_cache' not in config:
                    raise ValueError("If postoffice.dsn is in config, then "
                                     "postoffice.blob_cache is required.")
                po_uri = self._write_zconfig(
                    tmp_folder, 'postoffice.conf', config['postoffice.dsn'],
                    config['postoffice.blob_cache'])
        if po_uri:
            config['postoffice.zodb_uri'] = po_uri
            config['postoffice.queue'] = name

        pg_dsn = self.options.get('pgtextindex.dsn')
        if pg_dsn is None:
            pg_dsn = self.options.get('dsn')
        if pg_dsn is not None:
            config['pgtextindex.dsn'] = pg_dsn

        instance = make_karl_instance(name, config, uri)
        self._instance = instance
        self._uri = uri
        return instance

    def _write_zconfig(self, tmp_folder, fname, dsn, blob_cache):
        path = os.path.join(tmp_folder, fname)
        uri = 'zconfig://%s#main' % path
        zconfig = zconfig_template % dict(dsn=dsn, blob_cache=blob_cache)
        with open(path, 'w') as f:
            f.write(zconfig)
        return uri

    def __del__(self):
        if self._tmp_folder is not None:
            shutil.rmtree(self._tmp_folder)


def make_karl_instance(name, global_config, uri):
    db = db_from_uri(uri)
    conn = db.open()
    root = conn.root()

    config = global_config.copy()
    config.update(hardwired_config)
    instance_config = root.get('instance_config', None)
    if instance_config is None:
        instance_config = PersistentMapping(default_instance_config)
        root['instance_config'] = instance_config
    config.update(instance_config)
    transaction.commit()
    conn.close()
    db.close()
    del db, conn, root

    def appmaker(folder, name='site'):
        if name not in folder:
            bootstrapper = queryUtility(IBootstrapper, default=populate)
            bootstrapper(folder, name)

            # Use pgtextindex
            if 'pgtextindex.dsn' in config:
                site = folder.get(name)
                index = KarlPGTextIndex(get_weighted_textrepr)
                site.catalog['texts'] = index

            transaction.commit()

        return folder[name]

    # paster app config callback
    get_root = PersistentApplicationFinder(uri, appmaker)

    # Set up logging
    config['get_current_instance'] = get_current_instance
    configure_log(**config)
    set_subsystem('karl')

    # Make BFG app
    pkg_name = config.get('package', None)
    if pkg_name is not None:
        __import__(pkg_name)
        package = sys.modules[pkg_name]
        app = bfg_make_app(get_root, package, options=config)
    else:
        filename = 'karl.includes:standalone.zcml'
        app = bfg_make_app(get_root, filename=filename, options=config)

    app.config = config
    return app


def make_who_middleware(app):
    config = app.config
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


def make_karl_pipeline(app, global_config, uri):
    pipeline = app
    pipeline = make_who_middleware(pipeline)
    pipeline = make_tm(pipeline, global_config)
    pipeline = zodb_connector(pipeline, global_config, zodb_uri=uri)
    pipeline = error_log_middleware(pipeline)
    pipeline = ErrorPageFilter(pipeline, None, 'static', '')
    #pipeline = timeit(pipeline)
    return pipeline


def timeit(app):
    import time
    def middleware(environ, start_response):
        start_time = time.time()
        try:
            return app(environ, start_response)
        finally:
            print "Requests per second: %4.2f %s" % (1.0 / (
                time.time() - start_time), environ['PATH_INFO'])
    return middleware


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
}

# Hardwired for baby Karls
hardwired_config = {
    'jquery_dev_mode': False,
    'debug': False,
    'reload_templates': False,
    'js_devel_mode': False,
    'static_postfix': '/static',
    'upload_limit': 0,  # XXX ???
    'min_pw_length': 8,
    'selectable_groups': 'group.KarlStaff group.KarlUserAdmin group.KarlAdmin',
    'aspell_executable': 'aspell',
    'aspell_max_words': 5000,
    'aspell_languages': 'en',
}

zconfig_template = """
%%import relstorage
<zodb main>
  cache-size 100000
  <relstorage>
    <postgresql>
      dsn %(dsn)s
    </postgresql>
    shared-blob-dir False
    blob-dir %(blob_cache)s
    keep-history false
  </relstorage>
</zodb>
"""