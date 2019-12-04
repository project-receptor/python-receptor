import logging
import time
import asyncio

from prometheus_client import start_http_server

from .controller import Controller

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
        controller.enable_server(config.node_listen_address,
                                 config.node_listen_port)
    for peer in config.node_peers:
        controller.loop.create_task(controller.add_peer(peer))
    if config.node_keepalive_interval > 1:
        controller.loop.create_task(node_keepalive())
    controller.loop.create_task(controller.receptor.watch_expire())
    controller.run()


def run_as_controller(config):
    controller = Controller(config)
    if config.controller_stats_enable:
        logger.info(f'Starting stats on port {config.node_stats_port}')
        start_http_server(config.controller_stats_port)
    controller.enable_server(config.controller_listen_address,
                             config.controller_listen_port)
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
        await controller.add_peer(config.ping_peer)
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
            await controller.ping(config.ping_recipient)
            await asyncio.sleep(config.ping_delay)

    logger.info(f'Sending ping to {config.ping_recipient} via {config.ping_peer}.')
    controller = Controller(config)
    controller.run(ping_entrypoint)


def run_as_send(config):
    pass
