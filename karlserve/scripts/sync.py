import logging

from karlserve.db import sync
from karlserve.db import UnsafeOperationError
from karlserve.storage import storage_from_config

log = logging.getLogger(__name__)

def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Maintain warm backup of another installation of Karl.')
    parser.add_argument('-f', '--force', action='store_true',
                        help='Force sync even if data would be lost in the '
                        'destination database.')
    helpers['config_choose_instances'](parser)
    parser.set_defaults(func=main, parser=parser, subsystem='mailin')


def main(args):
    for name in args.instances:
        sync_instance(args, name)


def sync_instance(args, name):
    instance = args.get_instance(name)

    src = storage_from_config(instance.config, 'sync')
    if src is None:
        log.warn("Skipping instance: %s: not configured for sync.", name)
        return
    dst = storage_from_config(instance.config)

    try:
        tid = sync(src, dst, instance.last_sync_tid, not args.force)
        instance.last_sync_tid = tid
    except UnsafeOperationError, e:
        msg = "%s: %s  Use --force to proceed anyway." % (name, str(e))
        args.parser.error(msg)

