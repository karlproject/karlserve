import os
import sys

from paste.script.serve import ServeCommand


def config_parser(subparsers, **helpers):
    parser = subparsers.add_parser(
        'serve', help='Serve the application using Paste HTTP server.')
    parser.set_defaults(func=main, parser=parser)


def main(args):
    os.environ['PASTE_CONFIG_FILE'] = args.config

    cmd = ServeCommand('karlserve serve')
    exit_code = cmd.run([])
    sys.exit(exit_code)
