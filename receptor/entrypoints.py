import datetime
import json
import logging
import sys
import time
import asyncio

from prometheus_client import start_http_server

from .receptor import Receptor
from .controller import Controller
from . import exceptions
from . import node

logger = logging.getLogger(__name__)


def run_as_node(config):
    receptor = Receptor(config)
    logger.info(f'Running as Receptor node with ID: {receptor.node_id}')
    if config.node_stats_enable:
        logger.info(f'Starting stats on port {config.node_stats_port}')
        start_http_server(config.node_stats_port)
    node.mainloop(receptor, config.node_ping_interval)


def run_as_controller(config):
    controller = Controller(config)
    controller.enable_server(config.controller_listen_address,
                             config.controller_listen_port)
    controller.run()


def run_as_ping(config):
    async def read_responses():
        while True:
            payload = await controller.recv()
            print("{}".format(payload))

    async def do_ping():
        await asyncio.sleep(5)
        await controller.ping(config.ping_recipient)

    logger.info(f'Sending ping to {config.ping_recipient} via {config.ping_peer}.')
    controller = Controller(config)
    controller.loop.create_task(read_responses())
    controller.add_peer(config.ping_peer)
    controller.loop.create_task(do_ping())
    controller.run()
    
# def run_as_ping(config):
#     logger.info(f'Sending ping to {config.ping_recipient}.')
#     sock = controller.connect_to_socket(config.ping_socket_path)

#     try:
#         pings_sent = 0
#         while True:
#             now = datetime.datetime.utcnow()
#             response = controller.send_directive('receptor:ping', config.ping_recipient, now.isoformat(), sock)
#             resp_json = json.loads(response)
#             if 'code' in resp_json and resp_json['code'] != 0:
#                 sys.stdout.buffer.write(b"Failed to ping node: %b\n" % (resp_json['raw_payload'].encode('utf-8'),))
#             else:
#                 sys.stdout.buffer.write(response + b"\n")
#             sys.stdout.flush()
#             pings_sent += 1
#             if config.ping_count != 0 and pings_sent >= config.ping_count:
#                 break
#             elif config.ping_delay > 0.0:
#                 time.sleep(config.ping_delay)
#     except KeyboardInterrupt:
#         pass
#     finally:
#         sock.close()

def run_as_send(config):
    pass
# def run_as_send(config):
#     logger.info(f'Sending a {config.send_directive} directive to {config.send_recipient}.')
#     sock = controller.connect_to_socket(config.send_socket_path)
#     try:
#         if config.send_directive in (None, ''):
#             raise exceptions.UnknownDirective("The directive cannot be left out when using send.")
#         else:
#             try:
#                 left, right = config.send_directive.split(':', 1)
#             except ValueError:
#                 raise exceptions.UnknownDirective("Invalid directive format (%s). Directives must be in the form `action:method`." % (config.send_directive,))
#         response = controller.send_directive(config.send_directive, config.send_recipient, config.send_payload, sock)
#         sys.stdout.buffer.write(response + b"\n")
#         sys.stdout.flush()
#     except KeyboardInterrupt:
#         pass
#     finally:
#         sock.close()
