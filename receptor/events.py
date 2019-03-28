import argparse
from .listener import listener_run
from .server import server_run


def main(sys_args=None):
    parser = argparse.ArgumentParser("receptor")
    parser.add_argument("--listen")
    parser.add_argument("--server")
    
    args = parser.parse_args(sys_args)
    if args.listen:
        listener_run()
    else:
        server_run()
