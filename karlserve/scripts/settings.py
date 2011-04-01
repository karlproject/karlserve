import transaction


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Manage instance configuration.')
    subparsers = parser.add_subparsers(
        title='command', help='Settings operations.')
    config_list_settings(subparsers, **helpers)
    config_set_setting(subparsers, **helpers)
    config_remove_setting(subparsers, **helpers)
    config_settings_from_config(subparsers, **helpers)


def config_list_settings(subparsers, **helpers):
    parser = subparsers.add_parser(
        'list', help='List instance settings.')
    parser.add_argument('inst', metavar='instance', help='Karl instance.')
    parser.set_defaults(func=list_settings, parser=parser)


def config_set_setting(subparsers, **helpers):
    parser = subparsers.add_parser(
        'set', help='Change a configuration setting.')
    parser.add_argument('inst', metavar='instance', help='Karl instance.')
    parser.add_argument('name', help='Name of setting to change.')
    parser.add_argument('value', help='New value of setting.')
    parser.set_defaults(func=set_setting, parser=parser)


def config_remove_setting(subparsers, **helpers):
    parser = subparsers.add_parser(
        'remove', help='Remove a configuration setting.')
    parser.add_argument('inst', metavar='instance', help='Karl instance.')
    parser.add_argument('name', help='Name of setting to remove.')
    parser.set_defaults(func=remove_setting, parser=parser)


def config_settings_from_config(subparsers, **helpers):
    parser = subparsers.add_parser(
        'from_config', help='Update settings from instance config.')
    parser.add_argument('inst', metavar='instance', help='Karl instance.')
    parser.set_defaults(func=settings_from_config, parser=parser)


def get_settings(args, instance):
    site, closer = args.get_root(instance)
    root = site._p_jar.root
    return root.instance_config


def list_settings(args):
    settings = get_settings(args, args.inst)
    for name in sorted(settings.keys()):
        print >> args.out, '%s = %s' % (name, settings[name])


def set_setting(args):
    settings = get_settings(args, args.inst)
    settings[args.name] = args.value
    print >> args.out, '%s has been changed to %s' % (
        args.name, settings[args.name])
    print >> args.out, ('Note that any running WSGI processes must be '
                        'restarted in order to see new settings.')
    transaction.commit()


def remove_setting(args):
    settings = get_settings(args, args.inst)
    if args.name not in settings:
        args.parser.error('No such setting: %s' % args.name)
    del settings[args.name]
    print >> args.out, 'Removed setting: %s' % args.name
    print >> args.out, ('Note that any running WSGI processes must be '
                        'restarted in order to see new settings.')
    transaction.commit()


def settings_from_config(args):
    instance = args.get_instance(args.inst)
    settings = get_settings(args, args.inst)
    for key, value in instance.config.items():
        if not key.startswith('settings.'):
            continue
        key = key[9:]  # elide 'settings.'
        value = value.strip()
        if value:
            settings[key] = value
        elif key in settings:
            del settings[key]

    transaction.commit()
    list_settings(args)

