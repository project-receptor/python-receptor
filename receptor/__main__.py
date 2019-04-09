import argparse
import datetime
import logging
import logging.config
from .config import ReceptorConfig, DEFAULT_CONFIG
from . import node
from . import controller
from receptor import Receptor

logger = logging.getLogger(__name__)


def map_args_to_config(args):
    to_return = {}
    if getattr(args, 'listen_address', None):
        to_return.setdefault('server', {})['address'] = args.listen_address
    if getattr(args, 'listen_port', None):
        to_return.setdefault('server', {})['port'] = args.listen_port
    if getattr(args, 'server_disable', None):
        to_return.setdefault('server', {})['server_disable'] = args.server_disable
    if getattr(args, 'peer', None):
        to_return['peers'] = {peer: '' for peer in args.peer}
    if getattr(args, 'node_id', None):
        to_return.setdefault('receptor', {})['node_id'] = args.node_id
    return to_return


def run_as_controller(args):
    config = ReceptorConfig(cmdline_args=map_args_to_config(args))
    receptor = Receptor(config)
    logger.info(f'Starting up as node ID {receptor.node_id}')
    controller.mainloop(receptor, args.listen_address, args.listen_port, args.socket_path)


def run_as_ping(args):
    logger.info(f'Sending ping to {args.recipient}.')
    now = datetime.datetime.utcnow()
    controller.send_directive('receptor:ping', args.recipient, now.isoformat(), args.socket_path)


def run_as_send(args):
    logger.info(f'Sending a {args.directive} directive to {args.recipient}.')
    controller.send_directive(args.directive, args.recipient, args.payload, args.socket_path)


def run_as_node(args):
    config = ReceptorConfig(args.config, map_args_to_config(args))
    receptor = Receptor(config)
    logger.info("Running as Receptor node with ID: {}".format(receptor.node_id))
    node.mainloop(receptor, args.ping_interval)


def main(args=None):
    parser = argparse.ArgumentParser("receptor")
    parser.add_argument(
        "-c", "--config", default="./receptor.conf",
        help='Path to configuration file')
    parser.add_argument(
        "--debug", action="store_true", default=False,
        help='Emit debugging output')

    subparsers = parser.add_subparsers(
        title='subcommands')
    
    subparser_node = subparsers.add_parser(
        'node',
        help='Run a Receptor node')
    subparser_node.add_argument(
        "--listen-address",
        help=f'Set/override IP address to listen on. If not set here or in a config file, the default is {DEFAULT_CONFIG["server"]["address"]}')
    subparser_node.add_argument(
        "--listen-port",
        help=f'Set/override TCP port to listen on. If not set here or in a config file, the default is {DEFAULT_CONFIG["server"]["port"]}')
    subparser_node.add_argument(
        "-p", "--peer", action='append',
        help=f'Set/override peer nodes/controllers to connect to. Use multiple times for multiple peers.')
    subparser_node.add_argument(
        "--node-id",
        help='Set/override node identifier. If unspecified here or in a config file, one will be automatically generated.')
    subparser_node.add_argument(
        "--server-disable", action="store_true", default=False,
        help="Disable the server function and only connect to configured peers.")
    subparser_node.add_argument(
        '--ping-interval', metavar="N", type=int,
        help="If specified, the node will ping all other known nodes in the mesh every N seconds."
    )
    subparser_node.set_defaults(func=run_as_node)

    subparser_controller = subparsers.add_parser(
        'controller',
        help='Run a Receptor controller'
    )
    subparser_controller.add_argument(
        '--socket-path', default='./controller.sock',
        help='Path to control socket'
    )
    subparser_controller.add_argument(
        "--listen-address",
        help=f'Set/override IP address to listen on. If not set here or in a config file, the default is {DEFAULT_CONFIG["server"]["address"]}')
    subparser_controller.add_argument(
        "--listen-port",
        help=f'Set/override TCP port to listen on. If not set here or in a config file, the default is {DEFAULT_CONFIG["server"]["port"]}')
    subparser_controller.add_argument(
        "--node-id",
        help='Set/override node identifier. If unspecified here or in a config file, one will be automatically generated.')
    subparser_controller.set_defaults(func=run_as_controller)

    subparser_ping = subparsers.add_parser(
        'ping',
        help='Tell the local controller to ping a node'
    )
    subparser_ping.add_argument(
        '--socket-path', default='./controller.sock',
        help='Path to control socket'
    )
    subparser_ping.add_argument(
        'recipient',
        help='Node ID of the Receptor node or controller to ping'
    )
    subparser_ping.set_defaults(func=run_as_ping)

    subparser_send = subparsers.add_parser(
        'send',
        help='Send a directive to a node'
    )
    subparser_send.add_argument(
        '--socket-path', default='./controller.sock',
        help='Path to control socket'
    )
    subparser_send.add_argument(
        '--directive',
        help='Directive to send'
    )
    subparser_send.add_argument(
        '--destination',
        help='Node ID of the Receptor node or controller to direct'
    )
    subparser_send.add_argument(
        'payload',
        help='Payload of the directive to send. Use - for stdin.'
    )
    subparser_send.set_defaults(func=run_as_send)
   

    args = parser.parse_args(args)
    
    logging.config.dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'verbose': {
                    'format': '{levelname} {asctime} {module} {message}',
                    'style': '{',
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'verbose'
                },
            },
            'loggers': {
                'receptor': {
                    'handlers': ['console'],
                    'level': 'DEBUG' if args.debug else 'INFO',
                },
            },
        }
    )
    args.func(args)


if __name__ == '__main__':
    # We were run with python -m
    main()
