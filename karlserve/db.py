

class UnsafeOperationError(Exception):
    pass


def sync(src, dst, last_sync_txid=None, safe=True):
    """
    Copies transactions from ZODB `src` to ZODB `dst`. Specifying
    `last_sync_txid` can allow only transactions which are more recent to be
    copied. If `safe` is `True`, no data will be overwritten in the dst. In
    safe mode, the destination database must either be empty or, if
    `last_sync_txid` is specified, have no transactions more recent than the
    last sync.  Any opeation that would cause data to be overwritten in safe
    mode will cause an `UnsafeOperationError` to be raised.

    In non-safe mode, `sync` is willing to overwrite the destination database.
    If `last_sync_txid` is not specified and `dst` is not empty, `dst` will
    first be cleared before copying transactions. If `last_sync_txid` is
    specified, any transactions in `dst` later than the last sync will be
    rolled back before copying new transactions from `src`.  This will not work
    in history-free databases.  If a history free database has transactions
    newer than the last sync, this is considered an error and
    `UnsafeOperationError` will be raised.  To force sync of a history free
    database with modifications, specify `None` for `last_sync_txid`.
    """