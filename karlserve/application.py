import logging
import os
import time

from pyramid.config import Configurator
from pyramid.exceptions import NotFound
from repoze.depinj import lookup

from karlserve.instance import get_current_instance
from karlserve.instance import get_instances
from karlserve.instance import set_current_instance
from karlserve.log import configure_log
from karlserve.scripts.utils import shell_capture

log = logging.getLogger(__name__)


def _require_settings(settings, *names):
    for name in names:
        if name not in settings:
            raise ValueError("Must define '%s' in configuration" % name)


def _require_externals(*exes):
    for exe in exes:
        which = shell_capture('which %s' % exe).strip()
        if not which or not os.path.exists(which):
            log.warn("Missing external program: %s", exe)
            log.warn("Some functionality may not work.")


def make_app(global_config, **local_config):
    settings = global_config.copy()
    settings.update(local_config)

    _require_settings(settings,
        'instances_config',
        'who_secret',
        'who_cookie',
        'var',
    )

    _require_externals(
        'aspell',
        'pdftotext',
        'ppthtml',
        'ps2ascii',
        'rtf2xml',
        'xls2csv',
        'wvWare',
    )

    var = os.path.abspath(settings['var'])
    if 'mail_queue_path' not in settings:
        settings['mail_queue_path'] = os.path.join(var, 'mail_queue')
    if 'error_monitor_dir' not in settings:
        settings['error_monitor_dir'] = os.path.join(var, 'errors')
    if 'blob_cache' not in settings:
        settings['blob_cache'] = os.path.join(var, 'blob_cache')
    if 'var_instance' not in settings:
        settings['var_instance'] = os.path.join(var, 'instance')
    if 'var_tmp' not in settings:
        settings['var_tmp'] = os.path.join(var, 'tmp')

    # Configure timezone
    tz = settings.get('timezone')
    if tz is not None:
        os.environ['TZ'] = tz
        time.tzset()

    # Set up logging
    log_config = settings.copy()
    log_config['get_current_instance'] = get_current_instance
    configure_log(**log_config)

    # Configure repoze.bfg application
    config = lookup(Configurator)(settings=settings)
    config.add_route('sites', '/*subpath')
    config.add_view(site_dispatch, route_name='sites')

    app = config.make_wsgi_app()
    return app


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

    # nginx likes to set script name to '/' with screws up everybody
    # trying to write urls and causes them to add an extra slash
    if len(request.script_name) == 1:
        request.script_name = ''

    # See if we're in a virtual hosting environment
    name = instances.get_virtual_host(host)
    if not name and path:
        # We are not in a virtual hosting environment, so the first element of
        # the path_info is the name of the instance.
        name = path.pop(0)

        # Get the Karl instance to dispatch to
        instance = instances.get(name)

        # If we found the instance, rewrite paths for subrequest
        if instance is not None:
            script_name = '/'.join((request.script_name, name))
            path_info = '/' + '/'.join(path)
            request.script_name = script_name
            request.path_info = path_info

    else:
        # Get the Karl instance to dispatch to
        instance =  instances.get(name)

    # If we still don't have an instance, see if one is defined as the root
    # instance.
    if instance is None:
        name = instances.root_instance
        if name is not None:
            instance = instances.get(name)

    if instance is None:
        raise NotFound

    # Dispatch
    set_current_instance(name)
    return request.get_response(instance.pipeline())
