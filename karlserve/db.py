import logging
from ZODB.utils import p64
from ZODB.utils import u64

log = logging.getLogger(__name__)


class UnsafeOperationError(Exception):
    pass


def sync(src, dst, last_sync_tid=None, safe=True):
    """
    Copies transactions from ZODB `src` to ZODB `dst`. Specifying
    `last_sync_tid` can allow only transactions which are more recent to be
    copied. If `safe` is `True`, no data will be overwritten in the dst. In
    safe mode, the destination database must either be empty or, if
    `last_sync_tid` is specified, have no transactions more recent than the
    last sync.  Any opeation that would cause data to be overwritten in safe
    mode will cause an `UnsafeOperationError` to be raised.

    In non-safe mode, `sync` is willing to overwrite the destination database.
    If `last_sync_tid` is not specified and `dst` is not empty, `dst` will
    first be cleared before copying transactions. If `last_sync_tid` is
    specified, any transactions in `dst` later than the last sync will be
    rolled back before copying new transactions from `src`.  This will not work
    in history-free databases.  If a history free database has transactions
    newer than the last sync, this is considered an error and
    `UnsafeOperationError` will be raised.  To force sync of a history free
    database with modifications, specify `None` for `last_sync_tid`.
    """
    has_data = _storage_has_data(dst)
    if last_sync_tid is None:
        if has_data:
            if safe:
                raise UnsafeOperationError(
                    "Destination database is not empty.")
            else:
                dst.zap_all()

    elif has_data:
        latest_tid = _get_latest_tid_int(dst)
        if latest_tid != last_sync_tid:
            if safe:
                raise UnsafeOperationError(
                    "Destination database has modifications.")
            else:
                raise NotImplementedError(
                    "I don't know how to roll back transactions yet.")
        src = _StorageSlice(src, last_sync_tid)

    log.info("Copying transactions...")
    dst.copyTransactionsFrom(src)
    log.info("Finished copying transactions.")

    return _get_latest_tid_int(dst)


def _storage_has_data(storage):
    i = storage.iterator()
    try:
        if hasattr(i, 'next'):
            # New iterator API
            i.next()
        else:
            # Old index lookup API
            i[0]
    except (IndexError, StopIteration):
        return False
    return True


def _get_latest_tid_int(storage):
    iterator = storage.iterator()
    adapter = getattr(storage, '_adapter', None)
    if adapter is not None:
        # Use efficient private API in relstorage
        # XXX Is it thread safe to grab the cursor like this?
        txncontrol = getattr(adapter, 'txncontrol', None)
        cursor = getattr(storage, '_store_cursor', None)
        if txncontrol is not None and cursor is not None:
            return txncontrol.get_tid(cursor)

    # Not relstorage, use brute force scan
    log.info("Searching for latest transaction id...")
    for tx in iterator:
        pass
    log.info("Latest transaction id: %d", u64(tx.tid))
    return u64(tx.tid)


class _StorageSlice(object):

    def __init__(self, storage, tid):
        self.storage = storage
        self.start = p64(tid + 1)

    def iterator(self):
        i = self.storage.iterator(self.start)
        for tx in i:
            yield tx
