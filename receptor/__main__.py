import argparse
import logging
import logging.config
from .config import ReceptorConfig, DEFAULT_CONFIG
from .node import mainloop
from receptor import Receptor

logger = logging.getLogger(__name__)


def map_args_to_config(args):
    to_return = {}
    if args.listen_address:
        to_return.setdefault('server', {})['address'] = args.listen_address
    if args.listen_port:
        to_return.setdefault('server', {})['port'] = args.listen_port
    to_return.setdefault('server', {})['server_disable'] = args.server_disable
    if args.peer:
        to_return['peers'] = {peer: '' for peer in args.peer}
    if args.node_id:
        to_return.setdefault('receptor', {})['node_id'] = args.node_id
    return to_return


def run_as_node(args):
    config = ReceptorConfig(args.config, map_args_to_config(args))
    receptor = Receptor(config)
    logger.info("Running as Receptor node with ID: {}".format(receptor.node_id))
    mainloop(receptor)


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
        help='Run a receptor node')
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
    subparser_node.set_defaults(func=run_as_node)

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


main()
