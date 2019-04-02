import asyncio
import functools
import logging

from .protocol import BasicProtocol, create_peer
from .router import router

logger = logging.getLogger(__name__)

PING_INTERVAL = 15


def mainloop(config):
    loop = asyncio.get_event_loop()
    if not config.server.server_disable:
        listener = loop.create_server(
            lambda: BasicProtocol(loop),
            config.server.address, config.server.port)
        loop.create_task(listener)
        logger.info("Serving on %s:%s", config.server.address, config.server.port)
    for peer in config.peers:
        loop.create_task(create_peer(*peer.split(":", 1), loop))
    ping_time = (((int(loop.time()) + 1) // PING_INTERVAL) + 1) * PING_INTERVAL
    loop.call_at(ping_time, loop.create_task, send_pings_and_reschedule(loop, ping_time))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.stop()


async def send_pings_and_reschedule(loop, ping_time):
    logger.debug(f'Scheduling mesh ping.')
    for node_id in router.get_nodes():
        await router.ping_node(node_id)
    loop.call_at(ping_time + PING_INTERVAL, 
                 loop.create_task, send_pings_and_reschedule(
                     loop, ping_time + PING_INTERVAL))
