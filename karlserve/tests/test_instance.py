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
                        'karlserve.tests', 'instances.ini')}
        return cut(settings)

    def test_it(self):
        instances = self.make_one()
        self.assertEqual(instances.get('foo').options['dsn'], 'bar')
        self.assertEqual(instances.get('bar').options['dsn'], 'foo')
        self.assertEqual(instances.get_virtual_host('example.com:80'), 'bar')
        self.assertEqual(set(instances.get_names()), set(['foo', 'bar']))


class TestLazyInstance(unittest.TestCase):

    def setUp(self):
        from repoze.depinj import clear
        clear()

        def dummy_mki(name, global_config, uri):
            return name, global_config, uri

        def dummy_mkp(app, global_config, uri):
            return app, global_config, uri

        from repoze.depinj import inject
        from karlserve.instance import make_karl_instance
        from karlserve.instance import make_karl_pipeline
        inject(dummy_mki, make_karl_instance)
        inject(dummy_mkp, make_karl_pipeline)

    def tearDown(self):
        from repoze.depinj import clear
        clear()

    def make_one(self, **options):
        from karlserve.instance import LazyInstance as cut
        config = dict(blob_cache='var/blob_cache')
        config.update(options)
        return cut('instance', config, options)

    def test_pipeline_relstorage(self):
        instance = self.make_one(dsn='ha ha ha ha')
        app, global_config, uri = instance.pipeline()
        name, config, uri = app
        self.assertEqual(name, 'instance')
        self.assertEqual(global_config['blob_cache'], 'var/blob_cache')
        self.assertEqual(config['blob_cache'], 'var/blob_cache/instance')
        self.assertTrue(uri.startswith('zconfig:///'), uri)
        zconfig = open(uri[10:-5]).read()
        self.assertTrue('ha ha ha ha' in zconfig, zconfig)
        self.assertTrue('var/blob_cache/instance' in zconfig, zconfig)

    def test_pipeline_relstorage_w_postoffice(self):
        instance = self.make_one(**{'dsn': 'ha ha ha ha',
                                    'postoffice.dsn': 'ooh ooh ooh',
                                    'postoffice.blob_cache': 'var/po_blobs'})
        app, global_config, uri = instance.pipeline()
        name, config, uri = app
        self.assertTrue('postoffice.zodb_uri' in config, config)
        uri = config['postoffice.zodb_uri']
        self.assertTrue(uri.startswith('zconfig:///'), uri)
        zconfig = open(uri[10:-5]).read()
        self.assertTrue('ooh ooh ooh' in zconfig, zconfig)
        self.assertTrue('var/po_blobs' in zconfig, zconfig)
        self.assertEqual(config['postoffice.queue'], 'instance')

    def test_pipeline_relstorage_w_postoffice_missing_blob_cache(self):
        instance = self.make_one(**{'dsn': 'ha ha ha ha',
                                    'postoffice.dsn': 'ooh ooh ooh'})
        self.assertRaises(ValueError, instance.pipeline)


class Test_find_users(unittest.TestCase):

    def test_site_is_bootstrapped(self):
        from karlserve.instance import find_users
        class DummySite:
            users = object()
        jar = {'site': DummySite}
        self.assertEqual(find_users(jar), DummySite.users)

    def test_site_is_not_bootstrapped(self):
        from karlserve.instance import find_users
        from karlserve.instance import Users
        self.assertTrue(find_users({}), Users)


class Test_get_set_current_instance(unittest.TestCase):

    def test_it(self):
        from karlserve.instance import set_current_instance
        from karlserve.instance import get_current_instance
        set_current_instance('foo')
        self.assertEqual(get_current_instance(), 'foo')


class DummyInstances(object):

    def __init__(self, settings):
        self.settings = settings
