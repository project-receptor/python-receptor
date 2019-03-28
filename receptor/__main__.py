import argparse
import logging
from .events import mainloop
import receptor


logger = logging.getLogger(__name__)

def map_args_to_config(args):
    to_return = {}
    if args.listen_address:
        to_return.setdefault('server', {})['address'] = args.listen_address
    if args.listen_port:
        to_return.setdefault('server', {})['port'] = args.listen_port
    if args.peers:
        to_return['peers'] = {peer: '' for peer in args.peer}
    return to_return

def main(args=None):
    parser = argparse.ArgumentParser("receptor")
    parser.add_argument("-c", "--config", default="./receptor.conf")
    parser.add_argument("--listen-address")
    parser.add_argument("--listen-port")
    parser.add_argument("-p", "--peer", action='append')
    args = parser.parse_args(args)
    
    receptor.config = receptor.ReceptorConfig(args.config, map_args_to_config(args))
    mainloop(receptor.config.server.listen, receptor.config.server.port,
             peers=receptor.config.peers
    )


main()
