import BTrees
import ConfigParser
import logging
import os
import shutil
import tempfile
import transaction

from karl.utils import get_setting
from karlserve.utilities import feeds

log = logging.getLogger(__name__)


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Migrate an old style instance to use KarlServe.  Use '
        'sync to copy data before running migrate.'
    )
    parser.add_argument('inst', metavar='instance', help='New instance name.')
    parser.add_argument('karl_ini', help="Path to old karl.ini file.")
    parser.set_defaults(func=main, parser=parser)


def main(args):
    here = os.path.dirname(os.path.abspath(args.karl_ini))
    karl_ini = ConfigParser.ConfigParser({'here': here})
    karl_ini.read(args.karl_ini)
    site, closer = args.get_root(args.inst)
    migrate_settings(args, karl_ini, site)
    migrate_urchin(args, karl_ini, site)
    migrate_feeds(args, karl_ini, site)
    transaction.commit()


def migrate_settings(args, karl_ini, site, section='app:karl'):
    assert isinstance(karl_ini, ConfigParser.ConfigParser)
    config = dict([(k, v) for k, v in karl_ini.items('DEFAULT')])
    config.update(dict([(k, v) for k, v in karl_ini.items(section)]))
    settings = site._p_jar.root.instance_config
    for name in migratable_settings:
        is_list = False
        if name.startswith('+'):
            is_list = True
            name = name[1:]
        if name in config:
            value = config.get(name)
            if is_list:
                value = value.split()
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
                title = karl_ini.get(section, 'title').decode('UTF-8')
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
    'kaltura_player_uiconf_id',
    'kaltura_player_cache_st',
    '+error_monitor_subsystems',
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
