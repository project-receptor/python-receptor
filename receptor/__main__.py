import argparse
import logging
import logging.config
from .events import mainloop
import receptor

logger = logging.getLogger(__name__)


def map_args_to_config(args):
    to_return = {}
    if args.listen_address:
        to_return.setdefault('server', {})['address'] = args.listen_address
    if args.listen_port:
        to_return.setdefault('server', {})['port'] = args.listen_port
    if args.server_disable:
        to_return.setdefault('server', {})['server_disable'] = args.server_disable
    if args.peer:
        to_return['peers'] = {peer: '' for peer in args.peer}
    if args.node_id:
        to_return.setdefault('receptor', {})['node_id'] = args.node_id
    return to_return


def main(args=None):
    parser = argparse.ArgumentParser("receptor")
    parser.add_argument("-c", "--config", default="./receptor.conf")
    parser.add_argument("--listen-address")
    parser.add_argument("--listen-port")
    parser.add_argument("-p", "--peer", action='append')
    parser.add_argument("--debug", action="store_true", default=False)
    parser.add_argument("--node-id")
    parser.add_argument("--server-disable", action="store_true", default=False)
    parser.add_argument("--ping")
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
    receptor.config = receptor.ReceptorConfig(args.config, map_args_to_config(args))
    logger.info("Node Id: {}".format(receptor.get_node_id()))
    mainloop(receptor.config)


main()
