import logging
import time
import asyncio

from prometheus_client import start_http_server

from .receptor import Receptor
from .controller import Controller
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
    if config.controller_stats_enable:
        logger.info(f'Starting stats on port {config.node_stats_port}')
        start_http_server(config.controller_stats_port)
    controller.enable_server(config.controller_listen_address,
                             config.controller_listen_port)
    controller.run()


def run_as_ping(config):
    def ping_iter():
        if config.ping_count:
            for x in range(config.ping_count):
                yield x
        else:
            while True:
                yield 0

    async def handle_ping():
        read_task = controller.loop.create_task(read_responses())
        await controller.add_peer(config.ping_peer)
        start_wait = time.time()
        while not controller.receptor.router.node_is_known(config.ping_recipient) and (time.time() - start_wait < 5):
            await asyncio.sleep(0.1)
        await do_ping()
        await read_task

    async def read_responses():
        for _ in ping_iter():
            payload = await controller.recv()
            print("{}".format(payload))

    async def do_ping():
        for _ in ping_iter():
            await controller.ping(config.ping_recipient)
            await asyncio.sleep(config.ping_delay)

    logger.info(f'Sending ping to {config.ping_recipient} via {config.ping_peer}.')
    controller = Controller(config)
    controller.run(handle_ping)


def run_as_send(config):
    pass
