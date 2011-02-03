import logging

from repoze.zodbconn.uri import db_from_uri

from karl.utils import get_setting
from karlserve.db import sync
from karlserve.instance import set_current_instance
from karlserve.log import set_subsystem
from karlserve.storage import storage_from_config

log = logging.getLogger(__name__)

def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Maintain warm backup of another installation of Karl.')
    helpers['config_choose_instances'](parser)
    parser.set_defaults(func=main, parser=parser, subsystem='mailin')


def main(args):
    for name in args.instances:
        sync_instance(args, name)


def sync_instance(args, name):
    instance = args.get_instance(name)
    options = instance.options.copy()
    options.update(instance.config)

    src = storage_from_config(options, 'sync')
    if src is None:
        log.warn("Skipping instance: %s: not configured for sync.", name)
        return
    dst = storage_from_config(options)

    tid = sync(src, dst, instance.last_sync_tid)
    instance.last_sync_tid = tid

