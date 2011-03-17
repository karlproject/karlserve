import BTrees
import ConfigParser
import logging
import os
import shutil
import tempfile
import transaction

from repoze.bfg.traversal import find_model

from karl.models.site import get_weighted_textrepr
from karl.utils import find_catalog
from karl.utils import get_setting
from karlserve.utilities import feeds

from ZODB.POSException import ConflictError

try:
    from karlserve.textindex import KarlPGTextIndex
except ImportError:
    KarlPGTextIndex = None

log = logging.getLogger(__name__)

IF = BTrees.family32.IF

BATCH_SIZE = 500


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
    status = getattr(site, '_migration_status', None)
    use_pgtextindex = (KarlPGTextIndex is not None and
                       get_setting(site, 'pgtextindex.dsn'))
    if status is None:
        migrate_settings(args, karl_ini, site)
        migrate_urchin(args, karl_ini, site)
        migrate_feeds(args, karl_ini, site)
        if use_pgtextindex:
            switch_to_pgtextindex(args, site)
            print >> args.out, (
                "First stage of migration complete. Run again to complete "
                "switch to pgtextindex. Second stage can be run while site is "
                "live.")
        else:
            site._migration_status = 'done'
            print >> args.out, "Migration complete."
        transaction.commit()

    elif status == 'reindexing':
        reindex_text(args, site)

    elif status == 'done':
        print >> args.out, "Migration is finished.  No need to migrate."


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


def switch_to_pgtextindex(args, site):
    """
    It turns out, for OSI at least, that reindexing every document is too large
    of a transaction to fit in memory at once. This strategy seeks to address
    this problem along with a couple of other design goals:

      1) Production site can be running in read/write mode while documents
         are reindexed.

      2) This operation can be interrupted and pick back up where it left off.

    To accomplish this, in this function we merely create the new text index
    without yet replacing the old text index.  We then store the set of
    document ids of documents which need to be reindexed.  The 'reindex_text'
    function then reindexes documents in small batches, each batch in its own
    transaction.  Because the old index has not yet been replaced, users can
    use the site normally while this occurs.  When all documents have been
    reindexed, 'reindex_text' looks to see if any new documents have been
    indexed in the old index in the meantime and creates a new list of
    documents to reindex.  When the old_index and new_index are determined to
    contain the exact same set of document ids, then the new_index is put in
    place of the old_index and the migration is complete.
    """
    print >> args.out, "Converting to pgtextindex."
    catalog = find_catalog(site)
    old_index = catalog['texts']
    new_index = KarlPGTextIndex(get_weighted_textrepr)
    catalog['new_texts'] = new_index  # temporary location
    new_index.to_index = IF.Set()
    new_index.indexed = IF.Set()
    transaction.commit()
    site._migration_status = 'reindexing'


def reindex_text(args, site):
    catalog = find_catalog(site)
    old_index = catalog['texts']
    new_index = catalog['new_texts']

    done = False
    while not done:
        try:
            if len(new_index.to_index) == 0:
                calculate_docids_to_index(args, old_index, new_index)
                if len(new_index.to_index) == 0:
                    catalog['texts'] = new_index
                    del new_index.to_index
                    del new_index.indexed
                    site._migration_status = 'done'
                    done = True
                    print >> args.out, "Finished."
            else:
                reindex_batch(args, site)
            transaction.commit()
            site._p_jar.db().cacheMinimize()
        except ConflictError:
            log.warn("Conflict error: retrying....")
            transaction.abort()


def calculate_docids_to_index(args, old_index, new_index):
    print >> args.out, "Calculating docids to reindex..."
    old_docids = IF.Set(old_index.index._docwords.keys())
    new_docids = IF.Set(get_pg_docids(new_index))

    # Include both docids actually in the new index and docids we have tried to
    # index, since some docids might not actually be in the index if their
    # discriminator returns no value for texts.
    to_index = IF.difference(old_docids, new_docids)
    new_index.to_index = IF.difference(to_index, new_index.indexed)
    new_index.n_to_index = len(new_index.to_index)

    # Set of docids to unindex (user may have deleted something during reindex)
    # should be pretty small.  Just go ahead and handle that here.
    to_unindex = IF.difference(new_docids, old_docids)
    for docid in to_unindex:
        new_index.unindex_doc(docid)


def get_pg_docids(index):
    cursor = index.cursor
    cursor.execute("SELECT docid from %(table)s" % index._subs)
    for row in cursor:
        yield row[0]


def reindex_batch(args, site):
    catalog = find_catalog(site)
    addr = catalog.document_map.address_for_docid
    new_index = catalog['new_texts']
    to_index = new_index.to_index
    indexed = new_index.indexed
    l = new_index.n_to_index
    offset = l - len(to_index)
    batch = []
    for i in xrange(min(BATCH_SIZE, len(to_index))):
        batch.append(to_index[i])
    for i, docid in enumerate(batch):
        to_index.remove(docid)
        indexed.add(docid)
        path = addr(docid)
        try:
            doc = find_model(site, path)
        except KeyError:
            log.warn("No object at path: %s", path)
            continue

        print >> args.out, "Reindexing (%d/%d) %s" % (i + offset + 1, l, path)
        new_index.index_doc(docid, doc)
        deactivate = getattr(doc, '_p_deactivate', None)
        if deactivate is not None:
            deactivate()


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
