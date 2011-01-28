from code import interact
import sys

def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Open a debug session with a Karl instance.')
    parser.add_argument('-S', '--script', default=None,
                        help='Script to run. If not specified will start '
                        'an interactive session.')
    parser.add_argument('inst', metavar='instance', help='Instance name.')
    parser.set_defaults(func=main, parser=parser)


def main(args):
    root, closer = args.get_root(args.inst)
    script = args.script
    if script is None:
        cprt = ('Type "help" for more information. "root" is the karl '
                'root object.')
        banner = "Python %s on %s\n%s" % (sys.version, sys.platform, cprt)
        interact(banner, local={'root':root})
    else:
        code = compile(open(script).read(), script, 'exec')
        exec code in {'root': root}
