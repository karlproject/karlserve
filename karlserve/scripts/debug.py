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
    local_ns = {'app': args.app}
    cprt = ('Type "help" for more information. "app" is the karlserve BFG '
            'application.')
    if args.inst.lower() != 'none':
        root, closer = args.get_root(args.inst)
        cprt += ' "root" is the Karl instance root object.'
        local_ns['root'] = root
    script = args.script
    if script is None:
        banner = "Python %s on %s\n%s" % (sys.version, sys.platform, cprt)
        interact(banner, local=local_ns)
    else:
        code = compile(open(script).read(), script, 'exec')
        exec code in local_ns
