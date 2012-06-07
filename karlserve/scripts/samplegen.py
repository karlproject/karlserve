
from karlserve.instance import set_current_instance
from karl.utilities.samplegen import add_sample_community
from karl.utilities.samplegen import add_sample_users
import transaction


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Generate sample content in the database.')
    parser.add_argument('-c', '--communities', dest='communities',
        help='Number of communities to add (default 10)')
    parser.add_argument('--dry-run', dest='dryrun',
        action='store_true',
        help="Don't actually commit the transaction")
    parser.add_argument('-m', '--more-files', dest='more_files',
        action='store_true',
        help="Create many files in the first community (default false)")
    helpers['config_choose_instances'](parser)
    parser.set_defaults(func=main, parser=parser,
        communities=10, dryrun=False, more_files=False)


def main(args):
    for instance in args.instances:
        samplegen(args, instance)


def samplegen(args, instance):
    root, closer = args.get_root(instance)
    set_current_instance(instance)
    try:
        add_sample_users(root)
        for i in range(int(args.communities)):
            try:
                add_sample_community(root, more_files=(args.more_files and i==0))
            except TypeError:
                # fall back for old versions that do not support more_files
                add_sample_community(root)
    except:
        transaction.abort()
        raise
    else:
        if args.dryrun:
            transaction.abort()
        else:
            transaction.commit()
