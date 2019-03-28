import argparse
import logging
from configparser import SafeConfigParser
from .events import mainloop

logger = logging.getLogger(__name__)


def main(sys_args=None):
    parser = argparse.ArgumentParser("receptor")
    parser.add_argument("-c", "--config", default="./receptor.conf")
    parser.add_argument("--listen-address", default="0.0.0.0")
    parser.add_argument("--listen-port", default=8888)
    parser.add_argument("-p", "--peer", action='append')
    args = parser.parse_args(sys_args)
    config = SafeConfigParser()
    config.read([args.config])
    mainloop(config.get('server', 'listen', fallback=args.listen_address),
             config.get('server', 'port', fallback=args.listen_port),
             peers=args.peer if args.peer else [],
    )
