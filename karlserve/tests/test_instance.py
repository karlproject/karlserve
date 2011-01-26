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


class DummyInstances(object):

    def __init__(self, settings):
        self.settings = settings
