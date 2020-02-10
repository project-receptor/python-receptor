import logging
import time
import asyncio
import sys
import os

from prometheus_client import start_http_server

from .controller import Controller
from .messages import Message

logger = logging.getLogger(__name__)


def run_as_node(config):
    async def node_keepalive():
        # NOTE: I'm not really happy with this, I'd love to be able to await Peer(node).ping()
        # and then verify the status under a timeout rather than just throw away the result and
        # rely on the connection logic
        for node_id in controller.receptor.router.get_nodes():
            await controller.ping(node_id, expected_response=False)
        absolute_call_time = (((int(controller.loop.time()) + 1) // config.node_keepalive_interval) + 1) * config.node_keepalive_interval
        controller.loop.call_at(absolute_call_time,
                                controller.loop.create_task,
                                node_keepalive())

    controller = Controller(config)
    logger.info(f'Running as Receptor node with ID: {controller.receptor.node_id}')
    if config.node_stats_enable:
        logger.info(f'Starting stats on port {config.node_stats_port}')
        start_http_server(config.node_stats_port)
    if not config.node_server_disable:
        controller.enable_server(config.node_listen)
    for peer in config.node_peers:
        controller.add_peer(peer)
    if config.node_keepalive_interval > 1:
        controller.loop.create_task(node_keepalive())
    controller.loop.create_task(controller.receptor.watch_expire())
    controller.run()


def run_as_controller(config):
    controller = Controller(config)
    logger.info(f'Running as Receptor controller with ID: {controller.receptor.node_id}')
    if config.controller_stats_enable:
        logger.info(f'Starting stats on port {config.node_stats_port}')
        start_http_server(config.controller_stats_port)
    controller.enable_server(config.controller_listen)
    controller.loop.create_task(controller.receptor.watch_expire())
    controller.run()


def run_as_ping(config):
    def ping_iter():
        if config.ping_count:
            for x in range(config.ping_count):
                yield x
        else:
            while True:
                yield 0

    async def ping_entrypoint():
        read_task = controller.loop.create_task(read_responses())
        controller.add_peer(config.ping_peer)
        start_wait = time.time()
        while not controller.receptor.router.node_is_known(config.ping_recipient) and (time.time() - start_wait < 5):
            await asyncio.sleep(0.1)
        await send_pings()
        await read_task

    async def read_responses():
        for _ in ping_iter():
            payload = await controller.recv()
            print("{}".format(payload))

    async def send_pings():
        for _ in ping_iter():
            await controller.ping(config.ping_recipient, config.ping_flags or 0)
            await asyncio.sleep(config.ping_delay)

    logger.info(f'Sending ping to {config.ping_recipient} via {config.ping_peer}.')
    controller = Controller(config)
    controller.run(ping_entrypoint)


def run_as_send(config):
    async def send_entrypoint():
        read_task = controller.loop.create_task(read_responses())
        controller.add_peer(config.send_peer)
        start_wait = time.time()
        while not controller.receptor.router.node_is_known(config.ping_recipient) and (time.time() - start_wait < 5):
            await asyncio.sleep(0.1)
        msg = Message(config.send_recipient, config.send_directive)
        if config.send_payload == "-":
            msg.data(sys.stdin.buffer.read())
        elif os.path.exists(config.send_payload):
            msg.file(config.send_payload)
        else:
            if isinstance(config.send_payload, str):
                send_payload = config.send_payload.encode()
            else:
                send_payload = config.send_payload
            msg.data(send_payload)
        await controller.send(msg)
        await read_task

    async def read_responses():
        while True:
            print("{}".format(await controller.recv()))

    logger.info(f'Sending directive {config.send_directive} to {config.send_recipient} via {config.send_peer}')
    controller = Controller(config)
    controller.run(send_entrypoint)


def run_as_status(config):

    async def status_entrypoint():
        controller.add_peer(config.status_peer)
        start_wait = time.time()
        while not controller.receptor.router.node_is_known(config.status_peer) and (time.time() - start_wait < 5):
            await asyncio.sleep(0.1)
        print("Nodes:")
        print("  Myself:", controller.receptor.router.node_id)
        print("  Others:", ", ".join(list(controller.receptor.router.get_nodes())))
        print("Edges:")
        for edge in controller.receptor.router.get_edges():
            print("  ", edge)

    controller = Controller(config)
    controller.run(status_entrypoint)
