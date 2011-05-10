import unittest


class Test_make_app(unittest.TestCase):

    def setUp(self):
        from repoze.depinj import clear
        clear()

        from karlserve.application import Configurator
        from repoze.depinj import inject
        inject(DummyConfigurator, Configurator)

    def tearDown(self):
        from repoze.depinj import clear
        clear()

    def call_fut(self, global_config, config):
        from karlserve.application import make_app as fut
        return fut(global_config, **config)

    def test_it(self):
        from karlserve.application import site_dispatch
        global_config = {
            'instances_config': 'instances.ini',
            'error_monitor_dir': 'var/error',
            'mail_queue_path': 'var/mail/out',
            'who_secret': 'secret',
            'var': 'var',
            'timezone': 'TIMEZONE',
        }
        config = {
            'who_secret': 'really secret',
            'who_cookie': 'terces',
            'blob_cache': 'var/blob_cache',
        }
        settings = global_config.copy()
        settings.update(config)
        app = self.call_fut(global_config, config)
        app_settings = app.registry.settings
        self.failUnless(app_settings['var_instance'].endswith('/var/instance'))
        del app_settings['var_instance']
        self.failUnless(app_settings['var_tmp'].endswith('/var/tmp'))
        del app_settings['var_tmp']
        self.assertEqual(app.registry.settings, settings)
        self.assertEqual(settings['instances_config'], 'instances.ini')
        self.assertEqual(settings['error_monitor_dir'], 'var/error')
        self.assertEqual(settings['mail_queue_path'], 'var/mail/out')
        self.assertEqual(settings['who_secret'], 'really secret')
        self.assertEqual(settings['who_cookie'], 'terces')
        self.assertEqual(settings['blob_cache'], 'var/blob_cache')
        self.assertEqual(app._added_routes,
                         [('sites', '/*subpath', site_dispatch)])
        import os
        self.assertEqual(os.environ['TZ'], 'TIMEZONE')

    def test_missing_config_options(self):
        self.assertRaises(ValueError, self.call_fut, {}, {})

    def test_var_defaults(self):
        global_config = {
            'instances_config': 'instances.ini',
            'who_secret': 'secret',
            'var': 'var',
        }
        config = {
            'who_secret': 'really secret',
            'who_cookie': 'terces',
        }
        app = self.call_fut(global_config, config)
        settings = app.registry.settings
        self.failUnless(settings['var_instance'].endswith('/var/instance'))
        self.failUnless(settings['error_monitor_dir'].endswith('/var/errors'))
        self.failUnless(settings['mail_queue_path'].endswith('/var/mail_queue'))
        self.failUnless(settings['blob_cache'].endswith('/var/blob_cache'))


class Test_site_dispatch(unittest.TestCase):

    def setUp(self):
        from repoze.depinj import clear
        clear()

        from repoze.depinj import inject

    def tearDown(self):
        from repoze.depinj import clear
        clear()

    def call_fut(self, request):
        from karlserve.application import site_dispatch as fut
        return fut(request)

    def test_root(self):
        from repoze.bfg.exceptions import NotFound
        request = dummy_request('/')
        self.assertRaises(NotFound, self.call_fut, request)

    def test_not_found_instance(self):
        from repoze.bfg.exceptions import NotFound
        request = dummy_request('/instance/some/url')
        self.assertRaises(NotFound, self.call_fut, request)

    def test_dispatch_non_virtual(self):
        request = dummy_request('/foo/some/url')
        request, name = self.call_fut(request)
        self.assertEqual(name, 'foo')
        self.assertEqual(request.script_name, '/foo')
        self.assertEqual(request.path_info, '/some/url')

    def test_dispatch_non_virtual_slash_script_name(self):
        request = dummy_request('/foo/some/url')
        request.script_name = '/'

        request, name = self.call_fut(request)
        self.assertEqual(name, 'foo')
        self.assertEqual(request.script_name, '/foo')
        self.assertEqual(request.path_info, '/some/url')

    def test_dispatch_non_virtual_nested(self):
        request = dummy_request('/bar/some/url')
        request.script_name = '/foo'

        request, name = self.call_fut(request)
        self.assertEqual(name, 'bar')
        self.assertEqual(request.script_name, '/foo/bar')
        self.assertEqual(request.path_info, '/some/url')

    def test_dispatch_virtual(self):
        request = dummy_request('/some/url')
        instances = request.registry.settings['instances']
        instances['example.com:80'] = 'foo'
        request.host = 'example.com:80'
        request, name = self.call_fut(request)
        self.assertEqual(name, 'foo')


class DummyConfigurator(object):

    def __init__(self, settings):
        self.settings = settings
        self.registry = DummyRegistry()
        self._added_routes = []
        settings['bfg.setting'] = 'foo'

    def begin(self):
        pass

    def end(self):
        pass

    def add_route(self, name, path, view):
        self._added_routes.append((name, path, view))

    def make_wsgi_app(self):
        return self


class DummyRegistry(dict):
    pass


from repoze.bfg.testing import DummyRequest as BFGDummyRequest
class DummyRequest(object, BFGDummyRequest):

    def __init__(self, environ=None):
        BFGDummyRequest.__init__(self)
        self.registry.settings = {}
        self.registry.settings['instances'] = DummyInstances()
        if environ is not None:
            self.environ = environ
        self.environ['bfg.foo'] = 'bar'

    def get_response(self, app):
        return self, app

    @apply
    def script_name():
        def __get__(self):
            return self.environ['SCRIPT_NAME']

        def __set__(self, name):
            self.environ['SCRIPT_NAME'] = name

        return property(__get__, __set__)


def dummy_request(path):
    request = DummyRequest()
    request.matchdict = {
        'subpath': filter(None, path.split('/'))
    }
    return request


class DummyInstances(dict):
    root_instance = None

    def __init__(self):
        super(DummyInstances, self).__init__()
        self['foo'] = DummyInstance('foo')
        self['bar'] = DummyInstance('bar')

    get_virtual_host = dict.get


class DummyInstance(object):

    def __init__(self, name):
        self.name = name

    def pipeline(self):
        return self.name
