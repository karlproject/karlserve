import transaction

from repoze.bfg.traversal import model_path
from karl.content.models.blog import MailinTraceBlog
from karl.utils import find_communities


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Add a fake blog tool to community for receiving mailin '
                   'trace emails.'
    )
    parser.add_argument('inst', metavar='instance', help='Instance name.')
    parser.add_argument('community', help='Community name.')
    parser.add_argument('file', help='Path to file to touch when a tracer '
                                     'email is received.')
    parser.set_defaults(func=main, parser=parser)


def main(args):
    root, closer = args.get_root(args.inst)
    community = find_communities(root).get(args.community)
    if community is None:
        args.parser.error('Could not find community: %s' % args.community)

    blog = community.get('blog')
    if blog is not None:
        if len(blog) > 0:
            args.parser.error('Cannot replace blog with blog entries.')
        else:
            del community['blog']

    community['blog'] = blog = MailinTraceBlog()
    out = args.out
    print >> out, 'Added mailin trace tool at: %s' % model_path(blog)

    settings = root._p_jar.root.instance_config
    settings['mailin_trace_file'] = args.file
    print >> out, 'The mailin trace file is: %s' % args.file

    transaction.commit()
    print >> out, ('You must restart the mailin daemon in order for the new '
                   'settings to take effect.')
