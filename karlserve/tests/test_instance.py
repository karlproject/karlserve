import unittest


class Test_get_instances(unittest.TestCase):

    def setUp(self):
        from repoze.depinj import clear
        clear()

        from repoze.depinj import inject
        from karlserve.instance import Instances
        inject(DummyInstances, Instances)

    def tearDown(self):
        from repoze.depinj import clear
        clear()

    def test_it(self):
        from karlserve.instance import get_instances
        settings = {}
        instances = get_instances(settings)
        self.assertEqual(settings['instances'], instances)
        instances.iam = 'thisone'
        instances = get_instances(settings)
        self.assertEqual(instances.iam, 'thisone')


class TestInstances(unittest.TestCase):

    def make_one(self):
        import pkg_resources
        from karlserve.instance import Instances as cut
        settings = {'instances_config':
                    pkg_resources.resource_filename(
                        'karlserve.tests', 'instances.ini'),
                    'var_instance': 'var/instance',}
        return cut(settings)

    def test_it(self):
        instances = self.make_one()
        self.assertEqual(instances.get('foo').config['dsn'], 'bar')
        self.assertEqual(instances.get('foo').config['keep_history'], True)
        self.assertEqual(instances.get('bar').config['dsn'], 'foo')
        self.assertEqual(instances.get('bar').config['foo.keep_history'], False)
        self.assertEqual(instances.get_virtual_host('example.com:80'), 'bar')
        self.assertEqual(set(instances.get_names()), set(['foo', 'bar']))

    def test_close(self):
        closed = set()
        def dummy_closer(name):
            def close():
                closed.add(name)
            return close

        instances = self.make_one()
        instances.get('foo').close = dummy_closer('foo')
        instances.get('bar').close = dummy_closer('bar')
        instances.close()
        self.assertEqual(closed, set(['foo', 'bar']))

class TestLazyInstance(unittest.TestCase):

    def setUp(self):
        from repoze.depinj import clear
        clear()

        def dummy_mkp(app):
            return app.args

        def dummy_maintenance(arg):
            return 'maintenance app'

        from repoze.depinj import inject
        from karlserve.instance import make_karl_instance
        from karlserve.instance import make_karl_pipeline
        from karlserve.instance import maintenance
        inject(DummyApp, make_karl_instance)
        inject(dummy_mkp, make_karl_pipeline)
        inject(dummy_maintenance, maintenance)

        import os
        import tempfile
        self.tmp = tempfile.mkdtemp('.karlserve_tests')
        self.var = os.path.join(self.tmp, 'var')

    def tearDown(self):
        from repoze.depinj import clear
        clear()

        import shutil
        shutil.rmtree(self.tmp)

    def make_one(self, **options):
        from karlserve.instance import LazyInstance as cut
        config = dict(
            blob_cache='var/blob_cache',
            var_instance=self.var,
            var_tmp=self.var,
        )
        config.update(options)
        return cut('instance', config, options)

    def test_pipeline_relstorage(self):
        instance = self.make_one(dsn='ha ha ha ha')
        app = instance.pipeline()
        name, config, uri = app
        self.assertEqual(name, 'instance')
        self.assertEqual(config['blob_cache'], 'var/blob_cache/instance')
        self.assertTrue(uri.startswith('zconfig:///'), uri)
        zconfig = open(uri[10:]).read()
        self.assertTrue('ha ha ha ha' in zconfig, zconfig)
        self.assertTrue('cache-size 10000' in zconfig, zconfig)
        self.assertTrue('pool-size 3' in zconfig, zconfig)
        self.assertTrue('var/blob_cache/instance' in zconfig, zconfig)

    def test_pipeline_relstorage_w_cache_size(self):
        instance = self.make_one(**{
            'dsn': 'ha ha ha ha',
            'zodb.cache_size': '50000'})
        app = instance.pipeline()
        name, config, uri = app
        self.assertEqual(name, 'instance')
        self.assertEqual(config['blob_cache'], 'var/blob_cache/instance')
        self.assertTrue(uri.startswith('zconfig:///'), uri)
        zconfig = open(uri[10:]).read()
        self.assertTrue('ha ha ha ha' in zconfig, zconfig)
        self.assertTrue('cache-size 50000' in zconfig, zconfig)
        self.assertTrue('var/blob_cache/instance' in zconfig, zconfig)

    def test_pipeline_relstorage_w_pool_size(self):
        instance = self.make_one(**{
            'dsn': 'ha ha ha ha',
            'zodb.pool_size': '8'})
        app = instance.pipeline()
        name, config, uri = app
        self.assertEqual(name, 'instance')
        self.assertEqual(config['blob_cache'], 'var/blob_cache/instance')
        self.assertTrue(uri.startswith('zconfig:///'), uri)
        zconfig = open(uri[10:]).read()
        self.assertTrue('ha ha ha ha' in zconfig, zconfig)
        self.assertTrue('pool-size 8' in zconfig, zconfig)
        self.assertTrue('var/blob_cache/instance' in zconfig, zconfig)

    def test_pipeline_relstorage_w_memcached(self):
        instance = self.make_one(**{
            'dsn': 'ha ha ha ha',
            'relstorage.cache_servers': 'somehost:port',
        })
        app = instance.pipeline()
        name, config, uri = app
        self.assertEqual(name, 'instance')
        self.assertEqual(config['blob_cache'], 'var/blob_cache/instance')
        self.assertTrue(uri.startswith('zconfig:///'), uri)
        zconfig = open(uri[10:]).read()
        self.assertTrue('ha ha ha ha' in zconfig, zconfig)
        self.assertTrue('cache-prefix instance' in zconfig, zconfig)
        self.assertTrue('var/blob_cache/instance' in zconfig, zconfig)

    def test_pipeline_relstorage_w_memcached_and_prefix(self):
        instance = self.make_one(**{
            'dsn': 'ha ha ha ha',
            'relstorage.cache_servers': 'somehost:port',
            'relstorage.cache_prefix': 'testfoo',
        })
        app = instance.pipeline()
        name, config, uri = app
        self.assertEqual(name, 'instance')
        self.assertEqual(config['blob_cache'], 'var/blob_cache/instance')
        self.assertTrue(uri.startswith('zconfig:///'), uri)
        zconfig = open(uri[10:]).read()
        self.assertTrue('ha ha ha ha' in zconfig, zconfig)
        self.assertTrue('cache-prefix testfoo' in zconfig, zconfig)
        self.assertTrue('var/blob_cache/instance' in zconfig, zconfig)

    def test_pipeline_relstorage_w_postoffice(self):
        instance = self.make_one(**{'dsn': 'ha ha ha ha',
                                    'postoffice.dsn': 'ooh ooh ooh',
                                    'postoffice.blob_cache': 'var/po_blobs'})
        app = instance.pipeline()
        name, config, uri = app
        self.assertTrue('postoffice.zodb_uri' in config, config)
        uri = config['postoffice.zodb_uri']
        self.assertTrue(uri.startswith('zconfig:///'), uri)
        zconfig = open(uri[10:]).read()
        self.assertTrue('ooh ooh ooh' in zconfig, zconfig)
        self.assertTrue('var/po_blobs' in zconfig, zconfig)
        self.assertEqual(config['postoffice.queue'], 'instance')

    def test_pipeline_relstorage_w_postoffice_missing_blob_cache(self):
        instance = self.make_one(**{'dsn': 'ha ha ha ha',
                                    'postoffice.dsn': 'ooh ooh ooh'})
        self.assertRaises(ValueError, instance.pipeline)

    def test_mode(self):
        instance = self.make_one()
        self.assertEqual(instance.mode, 'NORMAL')
        instance.mode = 'MAINTENANCE'
        self.assertEqual(instance.mode, 'MAINTENANCE')
        instance.mode = 'NORMAL'
        self.assertEqual(instance.mode, 'NORMAL')

    def test_maintenance_mode(self):
        instance = self.make_one()
        instance.mode = 'MAINTENANCE'
        self.assertEqual(instance.pipeline(), 'maintenance app')

    def test_close(self):
        instance = self.make_one(dsn='ha ha ha')
        app = instance.instance()
        self.failIf(app.closed)
        instance.close()
        self.failUnless(app.closed)


class Test_get_set_current_instance(unittest.TestCase):

    def test_it(self):
        from karlserve.instance import set_current_instance
        from karlserve.instance import get_current_instance
        set_current_instance('foo')
        self.assertEqual(get_current_instance(), 'foo')


class DummyInstances(object):

    def __init__(self, settings):
        self.settings = settings


class DummyApp(object):
    closed = False

    def __init__(self, *args):
        self.args = args

    def close(self):
        self.closed = True

