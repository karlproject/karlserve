import BTrees
import logging
import transaction

from repoze.bfg.traversal import find_model
from ZODB.POSException import ConflictError

from karl.models.site import get_weighted_textrepr
from karl.utils import find_catalog
from karlserve.textindex import KarlPGTextIndex


log = logging.getLogger(__name__)

IF = BTrees.family32.IF

BATCH_SIZE = 500


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Switches text index of an instance to use '
        'repoze.pgtextindex.'
    )
    parser.add_argument('inst', metavar='instance', help='Instance to convert.')
    parser.add_argument('--check', action='store_true', default=False,
                        help='Prints whether or not repoze.pgtextindex is '
                        'currently in use. Performs no action.')
    parser.set_defaults(func=main, parser=parser)


def main(args):
    site, closer = args.get_root(args.inst)
    if args.check:
        if check(args, site):
            print >> args.out, "Using repoze.pgtextindex."
        else:
            print >> args.out, "Not using repoze.pgtextindex."
        return

    status = getattr(site, '_pgtextindex_status', None)
    if status == 'reindexing':
        reindex_text(args, site)
    elif check(args, site):
        print >> args.out, "Text index is already repoze.pgtextindex."
        print >> args.out, "Nothing to do."
    else:
        switch_to_pgtextindex(args, site)
        reindex_text(args, site)


def check(args, site):
    """
    Check to make sure we're not already using repoze.pgtextindex.
    """
    catalog = find_catalog(site)
    return isinstance(catalog['texts'], KarlPGTextIndex)


def switch_to_pgtextindex(args, site):
    """
    It turns out, for OSI at least, that reindexing every document is too large
    of a transaction to fit in memory at once. This strategy seeks to address
    this problem along with a couple of other design goals:

      1) Production site can be running in read/write mode while documents
         are reindexed.

      2) This operation can be interrupted and pick back up where it left off.

    To accomplish this, in this function we create the new text index without
    yet replacing the old text index. We then store the set of document ids of
    documents which need to be reindexed. The 'reindex_text' function then
    reindexes documents in small batches, each batch in its own transaction.
    Because the old index has not yet been replaced, users can use the site
    normally while this occurs. When all documents have been reindexed,
    'reindex_text' looks to see if any new documents have been indexed in the
    old index in the meantime and creates a new list of documents to reindex.
    When the old_index and new_index are determined to contain the exact same
    set of document ids, then the new_index is put in place of the old_index
    and the migration is complete.
    """
    log.info("Converting to repoze.pgtextindex.")
    catalog = find_catalog(site)
    old_index = catalog['texts']
    new_index = KarlPGTextIndex(get_weighted_textrepr)
    catalog['new_texts'] = new_index  # temporary location
    new_index.to_index = IF.Set()
    new_index.indexed = IF.Set()
    transaction.commit()
    site._pgtextindex_status = 'reindexing'


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
                    del site._pgtextindex_status
                    done = True
                    log.info("Finished.")
            else:
                reindex_batch(args, site)
            transaction.commit()
            site._p_jar.db().cacheMinimize()
        except ConflictError:
            log.warn("Conflict error: retrying....")
            transaction.abort()


def calculate_docids_to_index(args, old_index, new_index):
    log.info("Calculating docids to reindex...")
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

        log.info("Reindexing (%d/%d) %s", i + offset + 1, l, path)
        new_index.index_doc(docid, doc)
        deactivate = getattr(doc, '_p_deactivate', None)
        if deactivate is not None:
            deactivate()

