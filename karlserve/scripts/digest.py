from zope.component import queryUtility

from karlserve.instance import set_current_instance
from karlserve.log import set_subsystem
from karl.utilities.alerts import Alerts


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Send digest emails.')
    default_interval = 6 * 3600  # 6 hours
    helpers['config_daemon_mode'](parser, default_interval)
    helpers['config_choose_instances'](parser)
    parser.set_defaults(func=main, parser=parser, subsystem='digest')


def main(args):
    for instance in args.instances:
        digest(args, instance)


def digest(args, instance):
    root, closer = args.get_root(instance)
    set_current_instance(instance)
    set_subsystem('digest')
    alerts = Alerts()
    alerts.send_digests(root)
    closer()
