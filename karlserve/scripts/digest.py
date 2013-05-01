import logging

from karlserve.instance import set_current_instance
from karlserve.log import set_subsystem
from karl.utilities.alerts import Alerts

log = logging.getLogger(__name__)


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Send digest emails.')
    parser.add_argument('-f', '--frequency', dest='frequency', default='daily',
                      help='Digest frequency:  daily/weekly/biweekly.')
    default_interval = 6 * 3600  # 6 hours
    helpers['config_daemon_mode'](parser, default_interval)
    helpers['config_choose_instances'](parser)
    parser.set_defaults(func=main, parser=parser, subsystem='digest',
                        only_one=True)


def main(args):
    for instance in args.instances:
        if not args.is_normal_mode(instance):
            log.info("Skipping %s: Running in maintenance mode." % instance)
            continue
        digest(args, instance)


def digest(args, instance):
    root, closer = args.get_root(instance)
    set_current_instance(instance)
    set_subsystem('digest')
    alerts = Alerts()
    freq = args.frequency
    alerts.send_digests(root, freq)
    closer()
