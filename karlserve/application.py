from repoze.bfg.configuration import Configurator
from repoze.bfg.exceptions import NotFound
from repoze.depinj import lookup

from karlserve.instance import get_instances
from karlserve.instance import set_current_instance

from chameleon.core import config
config.DISK_CACHE = True

def _require_settings(settings, *names):
    for name in names:
        if name not in settings:
            raise ValueError("Must define '%s' in configuration" % name)

def make_app(global_config, **local_config):
    settings = global_config.copy()
    settings.update(local_config)

    _require_settings(settings,
        'instances_config',
        'error_monitor_dir',
        'mail_queue_path',
        'who_secret',
        'who_cookie',
        'blob_cache',
    )

    config = lookup(Configurator)(settings=settings.copy())
    config.begin()
    config.registry.settings = settings # emulate pyramid
    config.add_route(name='sites', path='/*subpath', view=site_dispatch)
    config.end()

    return config.make_wsgi_app()


def site_dispatch(request):
    instances = get_instances(request.registry.settings)
    path = list(request.matchdict.get('subpath'))
    host = request.host

    # Copy request, getting rid of bfg keys from the environ
    environ = request.environ.copy()
    for key in list(environ.keys()):
        if key.startswith('bfg.'):
            del environ[key]
    request = request.__class__(environ)

    # See if we're in a virtual hosting environment
    name = instances.get_virtual_host(host)
    if not name:
        # We are not in a virtual hosting environment, so the first element of
        # the path_info is the name of the instance.
        if not path:
            raise NotFound
        name = path.pop(0)

        # Rewrite paths for subrequest
        script_name = '/'.join((request.script_name, name))
        path_info = '/' + '/'.join(path)
        request.script_name = script_name
        request.path_info = path_info

    # Get the Karl instance to dispatch to
    instance =  instances.get(name)
    if instance is None:
        raise NotFound

    # Dispatch
    set_current_instance(name)
    return request.get_response(instance.pipeline())
