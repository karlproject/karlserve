import ConfigParser
import logging
import os
import shutil
import tempfile
import transaction

from relstorage import zodbconvert

from repoze.bfg.traversal import find_model

from karl.models.site import get_weighted_textrepr
from karl.utils import find_catalog
from karlserve.textindex import KarlPGTextIndex
from karlserve.utilities import feeds

log = logging.getLogger(__name__)


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Migrate an old style instance to use KarlServe.')
    parser.add_argument('inst', metavar='instance', help='New instance name.')
    parser.add_argument('karl_ini', help="Path to old karl.ini file.")
    parser.add_argument('karl_db', help="Path to old ZODB database file.")
    parser.add_argument('karl_blobs', help="Path to old blobs directory.")
    parser.set_defaults(func=main, parser=parser)


def main(args):
    migrate_database(args)

    here = os.path.dirname(os.path.abspath(args.karl_ini))
    karl_ini = ConfigParser.ConfigParser({'here': here})
    karl_ini.read(args.karl_ini)
    site, closer = args.get_root(args.inst)
    migrate_settings(args, karl_ini, site)
    migrate_urchin(args, karl_ini, site)
    migrate_feeds(args, karl_ini, site)
    switch_to_pgtextindex(args, site)
    transaction.commit()


def migrate_database(args):
    tmp = tempfile.mkdtemp('.karlserve')
    try:
        instance = args.get_instance(args.inst)
        blob_cache = instance.global_config['blob_cache']
        dsn = instance.options['dsn']
        config_file = os.path.join(tmp, 'zodbconvert.conf')
        open(config_file, 'w').write(config_template % {
            'blob_cache': blob_cache,
            'karl_db': args.karl_db,
            'karl_blobs': args.karl_blobs,
            'dsn': dsn,
        })
        zodbconvert.main(['zodbconvert', config_file], args.out.write)
    finally:
        shutil.rmtree(tmp)


def migrate_settings(args, karl_ini, site, section='app:karl'):
    assert isinstance(karl_ini, ConfigParser.ConfigParser)
    config = dict([(k, v) for k, v in karl_ini.items('DEFAULT')])
    config.update(dict([(k, v) for k, v in karl_ini.items(section)]))
    settings = site._p_jar.root.instance_config
    for name in migratable_settings:
        if name in config:
            value = config.get(name)
            print >> args.out, "Setting %s to %s" % (name, value)
            settings[name] = value
        else:
            print >> args.out, "Skipping %s" % name


def migrate_urchin(args, karl_ini, site):
    # Make sure urchin is actually used
    if not 'urchin' in karl_ini.get('pipeline:main', 'pipeline'):
        print >> args.out, "Urchin is not used by this site."
        return

    account = karl_ini.get('filter:urchin', 'account')
    print >> args.out, "Setting Urchin account:", account
    settings = site._p_jar.root.instance_config
    settings['urchin.account'] = account


def switch_to_pgtextindex(args, site):
    print >> args.out, "Converting to pgtextindex."
    catalog = find_catalog(site)
    addr = catalog.document_map.address_for_docid
    old_index = catalog['texts']
    new_index = KarlPGTextIndex(get_weighted_textrepr)
    docids = old_index.index._docwords.keys()
    for docid in docids:
        path = addr(docid)
        try:
            doc = find_model(site, path)
        except KeyError:
            log.warn("No object at path: %s", path)
            continue

        print >> args.out, "Reindexing %s" % path
        new_index.index_doc(docid, doc)

    catalog['texts'] = new_index


def migrate_feeds(args, karl_ini, site):
    if 'feeds' in site:
        del site['feeds']
    for section in karl_ini.sections():
        if section.startswith('feed:'):
            name = section[5:]
            uri = karl_ini.get(section, 'uri')
            if karl_ini.has_option(section, 'max'):
                max_entries = int(karl_ini.get(section, 'max'))
            else:
                max_entries = 0
            if karl_ini.has_option(section, 'title'):
                title = karl_ini.get(section, 'title')
            else:
                title = None
            print >> args.out, "Adding feed: ", name
            print >> args.out, "\turi:", uri
            print >> args.out, "\tmax:", max_entries
            print >> args.out, "\ttitle:", title
            feed = feeds.add_feed(site, name, uri, title, max_entries)
            feeds.update_feed(feed, log)


migratable_settings = [
    'package',
    'system_name',
    'system_email_domain',
    'admin_email',
    'offline_app_url',
    'postoffice.bounce_from_email',
    'staff_change_password_url',
    'forgot_password_url',
    'kaltura_enabled',
    'kaltura_partner_id',
    'kaltura_sub_partner_id',
    'kaltura_user_secret',
    'kaltura_admin_secret',
    'kaltura_client_session',
    'kaltura_kcw_uiconf_id',
    'kaltura_player_cache_st',
]


config_template = """
<filestorage source>
  path %(karl_db)s
  blob-dir %(karl_blobs)s
</filestorage>

<relstorage destination>
  <postgresql>
    dsn %(dsn)s
  </postgresql>
  shared-blob-dir False
  blob-dir %(blob_cache)s
  keep-history false
</relstorage>
"""