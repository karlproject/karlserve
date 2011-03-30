import unittest
from ZODB.utils import u64
from ZODB.utils import p64

class Test_sync(unittest.TestCase):
    _raise_on_undo = None

    def setUp(self):
        from karlserve import db
        self.save_DB = db.DB
        db.DB = DummyDB(self)

        self.save_transaction = db.transaction
        db.transaction = DummyTransactionManager()

    def tearDown(self):
        from karlserve import db
        db.DB = self.save_DB
        db.transaction = self.save_transaction

    def _call_fut(self, *args, **kw):
        from karlserve.db import sync as fut
        return fut(*args, **kw)

    def test_full_empty_dst(self):
        src = DummyStorage(make_transactions(*range(5)))
        dst = DummyStorage([])
        tid = self._call_fut(src, dst)
        self.assertEqual(dst.tids(), range(5))
        self.assertEqual(tid, 4)

    def test_full_empty_dst_and_src(self):
        src = DummyStorage([])
        dst = DummyStorage([])
        tid = self._call_fut(src, dst)
        self.assertEqual(dst.tids(), [])
        self.assertEqual(tid, None)

    def test_full_empty_dst_ancient_storage(self):
        src = AncientStorage(make_transactions(*range(5)))
        dst = AncientStorage([])
        tid = self._call_fut(src, dst)
        self.assertEqual(dst.tids(), range(5))
        self.assertEqual(tid, 4)

    def test_full_empty_dst_relstorage(self):
        src = DummyRelStorage(make_transactions(*range(5)))
        dst = DummyRelStorage([])
        tid = self._call_fut(src, dst)
        self.assertEqual(dst.tids(), range(5))
        self.assertEqual(tid, 4)

    def test_full_non_empty_dst(self):
        from karlserve.db import UnsafeOperationError
        src = DummyStorage(make_transactions(*range(5)))
        dst = DummyStorage(make_transactions(*range(5)))
        self.assertRaises(UnsafeOperationError, self._call_fut, src, dst)

    def test_full_non_empty_dst_unsafe(self):
        src = DummyStorage(make_transactions(*range(5)))
        dst = DummyStorage(make_transactions(2, 4, 6, 8))
        tid = self._call_fut(src, dst, safe=False)
        self.assertEqual(dst.tids(), range(5))
        self.assertEqual(tid, 4)

    def test_incremental(self):
        src = DummyStorage(make_transactions(*range(10)))
        dst = DummyStorage(make_transactions(*range(5)))
        tid = self._call_fut(src, dst, 4)
        self.assertEqual(tid, 9)
        self.assertEqual(dst.tids(), range(10))

    def test_incremental_dst_changed(self):
        from karlserve.db import UnsafeOperationError
        src = DummyStorage(make_transactions(*range(10)))
        dst = DummyStorage(make_transactions(*range(5)))
        self.assertRaises(UnsafeOperationError, self._call_fut, src, dst, 3)

    def test_incremental_dst_changed_unsafe(self):
        src = DummyStorage(make_transactions(0, 1, 2, 6, 8))
        dst = DummyStorage(make_transactions(1, 2, 3, 5))
        tid = self._call_fut(src, dst, 2, False)
        self.assertEqual(tid, 8)
        self.assertEqual(dst.undone, [5, 3])
        self.assertEqual(dst.tids(), [1, 2, 6, 8])

    def test_incremental_time_warp(self):
        src = DummyStorage(make_transactions(*range(10)))
        dst = DummyStorage(make_transactions(*range(5)))
        self.assertRaises(ValueError, self._call_fut, src, dst, 5)

    def test_attempt_incremental_do_full(self):
        src = DummyStorage(make_transactions(0, 1, 2, 6, 8))
        dst = DummyStorage(make_transactions(1, 3, 5))
        tid = self._call_fut(src, dst, 2, False)
        self.assertEqual(tid, 8)
        self.assertEqual(dst.undone, [])
        self.assertEqual(dst.tids(), [0, 1, 2, 6, 8])

    def test_attempt_incremental_undo_error(self):
        from ZODB.POSException import UndoError
        self._raise_on_undo = UndoError('no reason')
        src = DummyStorage(make_transactions(0, 1, 2, 6, 8))
        dst = DummyStorage(make_transactions(1, 2, 3, 5))
        tid = self._call_fut(src, dst, 2, False)
        self.assertEqual(tid, 8)
        self.assertEqual(dst.undone, [])
        self.assertEqual(dst.tids(), [0, 1, 2, 6, 8])

    def test_attempt_incremental_undo_not_implemented(self):
        self._raise_on_undo = NotImplementedError('no reason')
        src = DummyStorage(make_transactions(0, 1, 2, 6, 8))
        dst = DummyStorage(make_transactions(1, 2, 3, 5))
        tid = self._call_fut(src, dst, 2, False)
        self.assertEqual(tid, 8)
        self.assertEqual(dst.undone, [])
        self.assertEqual(dst.tids(), [0, 1, 2, 6, 8])


class TestStorageSlice(unittest.TestCase):

    def _make_one(self):
        from karlserve.db import _StorageSlice
        storage = DummyStorage(make_transactions(*range(5)))
        return _StorageSlice(storage, 2)

    def test_slice(self):
        slice = self._make_one()
        transactions = list(slice.iterator())
        tids = [u64(tx.tid) for tx in transactions]
        self.assertEqual(tids, [3, 4])

    def test_loadBlob(self):
        slice = self._make_one()
        self.assertEqual(slice.loadBlob(42), 'Oooh, a blob!')


class DummyStorage(object):

    def __init__(self, transactions):
        self.transactions = transactions
        self.undone = []

    def iterator(self, start=None):
        if start is not None:
            start = u64(start)
            index = len(self.transactions)
            for i, tx in enumerate(self.transactions):
                if u64(tx.tid) >= start:
                    index = i
                    break
            return iter(self.transactions[index:])
        return iter(self.transactions)

    def copyTransactionsFrom(self, src):
        self.transactions.extend(src.iterator())

    def tids(self):
        return [u64(tx.tid) for tx in self.transactions]

    def zap_all(self):
        self.transactions = []

    def loadBlob(self, blob_id):
        return 'Oooh, a blob!'


class DummyRelStorage(DummyStorage):

    @property
    def _adapter(self):
        return self

    @property
    def txncontrol(self):
        return self

    def _with_store(self, f):
        return f(None, None)

    def get_tid(self, cursor):
        return u64(self.transactions[-1].tid)


class AncientStorage(DummyStorage):

    def iterator(self, start=None):
        # Use old Python iterator protocol
        i = super(AncientStorage, self).iterator(start)
        return AncientIterator(i)


class AncientIterator:
    def __init__(self, i):
        self.i = list(i)

    def __getitem__(self, index):
        return self.i[index]


def make_transactions(*tids):
    return [DummyTransaction(tid) for tid in tids]


class DummyTransaction(object):

    def __init__(self, tid):
        self.tid = p64(tid)


def DummyDB(test):

    class DB(object):

        def __init__(self, storage):
            self.storage = storage

        def undo(self, tid):
            if test._raise_on_undo is not None:
                raise test._raise_on_undo

            import base64
            tid = base64.decodestring(tid + '\n')
            transactions = self.storage.transactions
            for i, tx in enumerate(transactions):
                if tx.tid == tid:
                    del transactions[i]
                    self.storage.undone.append(u64(tid))
                    return
            assert False, "No such tid." # pragma NO COVERAGE

        def close(self):
            pass

    return DB


class DummyTransactionManager(object):

    def commit(self):
        pass

