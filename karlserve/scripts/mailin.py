import logging
import transaction

from karl.utils import get_setting
from karl.utilities.mailin import MailinRunner2

from karlserve.instance import set_current_instance
from karlserve.log import set_subsystem

log = logging.getLogger(__name__)

def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Process incoming mail.')
    helpers['config_daemon_mode'](parser)
    helpers['config_choose_instances'](parser)
    parser.set_defaults(func=main, parser=parser, subsystem='mailin')


def main(args):
    for instance in args.instances:
        mailin(args, instance)


def mailin(args, instance):
    log.info("Processing mailin for %s" % instance)
    root, closer = args.get_root(instance)
    set_current_instance(instance)
    set_subsystem('mailin')

    zodb_uri = get_setting(root, 'postoffice.zodb_uri')
    zodb_path = get_setting(root, 'postoffice.zodb_path', '/postoffice')
    queue = get_setting(root, 'postoffice.queue')

    if zodb_uri is None:
        args.parser.error("postoffice.zodb_uri must be set in config file")

    if queue is None:
        args.parser.error("postoffice.queue must be set in config file")

    runner = MailinRunner2(root, zodb_uri, zodb_path, queue)
    try:
        runner()
        transaction.commit()

        p_jar = getattr(root, '_p_jar', None)
        if p_jar is not None:
            # Attempt to fix memory leak
            p_jar.db().cacheMinimize()

    except:
        transaction.abort()
        raise

    finally:
        closer()
        runner.close()
