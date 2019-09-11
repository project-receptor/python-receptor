import datetime
import json
import logging
import sys
import time

from .receptor import Receptor
from . import node
from . import controller

logger = logging.getLogger(__name__)


def run_as_controller(config):
    receptor = Receptor(config)
    logger.info(f'Starting up as node ID {receptor.node_id}')
    controller.mainloop(receptor, config.controller_socket_path)


def run_as_ping(config):
    logger.info(f'Sending ping to {config.ping_recipient}.')
    sock = controller.connect_to_socket(config.ping_socket_path)

    try:
        pings_sent = 0
        while True:
            now = datetime.datetime.utcnow()
            response = controller.send_directive('receptor:ping', config.ping_recipient, now.isoformat(), sock)
            resp_json = json.loads(response)
            if 'code' in resp_json and resp_json['code'] != 0:
                sys.stdout.buffer.write(b"Failed to ping node: %b\n" % (resp_json['payload'].encode('utf-8'),))
            else:
                sys.stdout.buffer.write(response + b"\n")
            sys.stdout.flush()
            pings_sent += 1
            if config.ping_count != 0 and pings_sent >= config.ping_count:
                break
            elif config.ping_delay > 0.0:
                time.sleep(config.ping_delay)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


def run_as_send(config):
    logger.info(f'Sending a {config.send_directive} directive to {config.send_recipient}.')
    sock = controller.connect_to_socket(config.send_socket_path)
    try:
        response = controller.send_directive(config.send_directive, config.send_recipient, config.send_payload, sock)
        sys.stdout.buffer.write(response + b"\n")
        sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


def run_as_node(config):
    receptor = Receptor(config)
    logger.info(f'Running as Receptor node with ID: {receptor.node_id}')
    node.mainloop(receptor, config.node_ping_interval)
