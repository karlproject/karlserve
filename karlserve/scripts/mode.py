
def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Show or change mode of instances.')
    helpers['config_choose_instances'](parser)
    parser.add_argument('-s', '--set',
                        help="Change mode.  Must be one of NORMAL, READONLY, "
                        "or MAINTENANCE.")
    parser.set_defaults(func=main, parser=parser)

_valid_values = [
    'NORMAL',
    'READONLY',
    'MAINTENANCE',
]

def main(args):
    set_to = args.set
    if set_to is not None:
        set_to = set_to.upper()
        if set_to not in _valid_values:
            args.parser.error("Mode must be NORMAL, READONLY or MAINTENANCE.")

    for name in args.instances:
        instance = args.get_instance(name)
        if set_to is not None:
            instance.mode = set_to
        print "%-14s %s" % (name, instance.mode)
