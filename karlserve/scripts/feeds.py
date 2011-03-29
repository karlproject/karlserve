from karlserve.instance import set_current_instance
from karlserve.log import set_subsystem
from karlserve.utilities import feeds

import logging
import transaction

log = logging.getLogger(__name__)


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Rss/Atom feed operations.')
    subparsers = parser.add_subparsers(title='command', help='Feed commands.')
    config_add_feed(subparsers, **helpers)
    config_list_feeds(subparsers, **helpers)
    config_remove_feed(subparsers, **helpers)
    config_edit_feed(subparsers, **helpers)
    config_update_feeds(subparsers, **helpers)


def config_add_feed(subparsers, **helpers):
    parser = subparsers.add_parser('add', help='Add a new feed.')
    parser.add_argument('inst', metavar='instance', help='Karl instance.')
    parser.add_argument('-t', '--title', help='Override title of feed.')
    parser.add_argument('-m', '--max', type=int, default=0,
                        help='Maximum number of entries to keep at a time.')
    parser.add_argument('name', help='Identifier of feed in database.')
    parser.add_argument('url', help='URL of feed.')
    parser.set_defaults(func=add_feed, parser=parser)


def config_edit_feed(subparsers, **helpers):
    parser = subparsers.add_parser('edit', help='Edit a feed.')
    parser.add_argument('inst', metavar='instance', help='Karl instance.')
    parser.add_argument('name', help='Identifier of feed in database.')
    parser.add_argument('-t', '--title', help='Override title of feed.')
    parser.add_argument('--use-feed-title', action='store_true',
                        help='Use feed title. Undoes previous override.')
    parser.add_argument('-m', '--max', type=int,
                        help='Maximum number of entries to keep at a time.')
    parser.add_argument('-u', '--url', help='URL of feed.')
    parser.set_defaults(func=edit_feed, parser=parser)


def config_list_feeds(subparsers, **helpers):
    parser = subparsers.add_parser('list', help='List feeds.')
    parser.add_argument('inst', metavar='instance', help='Karl instance.')
    parser.set_defaults(func=list_feeds, parser=parser)


def config_remove_feed(subparsers, **helpers):
    parser = subparsers.add_parser('remove', help='Remove a feed.')
    parser.add_argument('inst', metavar='instance', help='Karl instnace.')
    parser.add_argument('name', help='Name of feed.')
    parser.set_defaults(func=remove_feed, parser=parser)


def config_update_feeds(subparsers, **helpers):
    parser = subparsers.add_parser(
        'update', help='Get new entries from feeds.')
    default_interval = 1800  # 30 minutes
    helpers['config_daemon_mode'](parser, default_interval)
    helpers['config_choose_instances'](parser)
    parser.add_argument('-f', '--force', action='store_true',
                        help='Force reload of feed entries.')
    parser.set_defaults(func=update_feeds, parser=parser,
                        subsystem='update_feeds', only_one=True)


def add_feed(args):
    root, closer = args.get_root(args.inst)
    feed = get_feed(root, args.name)
    if feed is not None:
        args.parser.error("Feed already exists with name: %s" % args.name)
    feeds.add_feed(root, args.name, args.url, args.title, args.max)
    transaction.commit()


def edit_feed(args):
    root, closer = args.get_root(args.inst)
    feed = get_feed(root, args.name)
    if feed is None:
        args.parser.error("No such feed: %s"  % args.name)
    if args.max is not None:
        feed.max_entries = args.max
    if args.url is not None:
        feed.url = args.url
    if args.use_feed_title:
        feed.title = None
        feed.override_title = False
    elif args.title is not None:
        feed.title = args.title
        feed.override_title = True
    transaction.commit()


def remove_feed(args):
    root, closer = args.get_root(args.inst)
    feeds = root.get('feeds')
    if not feeds or args.name not in feeds:
        args.parser.error("No such feed: %s" % args.name)
    del feeds[args.name]
    transaction.commit()


def list_feeds(args):
    root, closer = args.get_root(args.inst)
    feeds = root.get('feeds')
    if feeds is None or len(feeds) == 0:
        print >> args.out, 'No feeds configured.'
        return
    for name in sorted(feeds.keys()):
        feed = feeds.get(name)
        print >> args.out, "%s:" % name
        print >> args.out, "\turl: %s" % feed.url
        print >> args.out, "\ttitle: %s" % feed.title
        print >> args.out, "\tmax entries: %d" % feed.max_entries


def update_feeds(args):
    for instance in args.instances:
        if not args.is_normal_mode(instance):
            log.info("Skipping %s: Running in maintenance mode." % instance)
            continue
        update_feeds_for_instance(args, instance)


def update_feeds_for_instance(args, instance):
    log.info("Updating feeds for %s", instance)
    root, closer = args.get_root(instance)
    set_current_instance(instance)
    set_subsystem('update_feeds')
    feeds.update_feeds(root, log, args.force)


def get_feed(root, name):
    container = root.get('feeds')
    if container is None:
        return None
    return container.get(name)
