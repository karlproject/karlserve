import sys
import transaction

from repoze.evolution import IEvolutionManager
from repoze.evolution import evolve_to_latest

from zope.component import getUtilitiesFor

from karlserve.instance import set_current_instance


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Bring database up to date with code.')
    parser.add_argument('--latest', action='store_true',
                        help='Update to latest versions.')
    helpers['config_choose_instances'](parser)
    parser.set_defaults(func=main, parser=parser)


def main(args):
    for instance in args.instances:
        evolve(args, instance)


def evolve(args, instance):
    print >> args.out, "=" * 78
    print >> args.out, "Instance: ", instance
    root, closer = args.get_root(instance)
    set_current_instance(instance)

    managers = list(getUtilitiesFor(IEvolutionManager))

    for pkg_name, factory in managers:
        __import__(pkg_name)
        pkg = sys.modules[pkg_name]
        VERSION = pkg.VERSION
        print >> args.out, 'Package %s' % pkg_name
        manager = factory(root, pkg_name, VERSION, 0)
        db_version = manager.get_db_version()
        print >> args.out, 'Code at software version %s' % VERSION
        print >> args.out, 'Database at version %s' % db_version
        if VERSION <= db_version:
            print >> args.out, 'Nothing to do'
        elif args.latest:
            evolve_to_latest(manager)
            ver = manager.get_db_version()
            print >> args.out, 'Evolved %s to %s' % (pkg_name, ver)
        else:
            print >> args.out, 'Not evolving (use --latest to do actual evolution)'
        print >> args.out, ''

    transaction.commit()
