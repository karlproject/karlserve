from repoze.sendmail.mailer import SMTPMailer
from repoze.sendmail.queue import QueueProcessor

from karlserve.log import set_subsystem


def config_parser(subparsers, **helpers):
    parser = subparsers.add_parser(
        'mailout', help='Send outgoing mail.')
    helpers['config_daemon_mode'](parser, 60)
    parser.add_argument('--server', '-s', default="localhost", metavar='HOST',
                        help='SMTP server host name.  Default is localhost.', )
    parser.add_argument('--port', '-P', type=int, default=25, metavar='PORT',
                        help='Port of SMTP server.  Default is 25.', )
    parser.add_argument('--username', '-u',
                        help='Username, if authentication is required')
    parser.add_argument('--password', '-p',
                        help='Password, if authentication is required')
    parser.add_argument('--force-tls', '-f', action='store_true',
                        help='Require that TLS be used.')
    parser.add_argument('--no-tls', '-n', action='store_true',
                        help='Require that TLS not be used.')
    parser.set_defaults(func=main, parser=parser, subsystem='mailout')


def main(args):
    queue_path = args.get_setting('mail_queue_path')
    set_subsystem('mailout')

    mailer = SMTPMailer(
        hostname=args.server,
        port=args.port,
        username=args.username,
        password=args.password,
        no_tls=args.no_tls,
        force_tls=args.force_tls
    )
    qp = QueueProcessor(mailer, queue_path)
    qp.send_messages()