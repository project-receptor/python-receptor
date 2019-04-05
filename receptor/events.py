import asyncio
import logging

from .protocol import BasicProtocol, create_peer

logger = logging.getLogger(__name__)

PING_INTERVAL = 15


def mainloop(receptor):
    loop = asyncio.get_event_loop()
    config = receptor.config
    if not config.server.server_disable:
        listener = loop.create_server(
            lambda: BasicProtocol(receptor, loop),
            config.server.address, config.server.port)
        loop.create_task(listener)
        logger.info("Serving on %s:%s", config.server.address, config.server.port)
    for peer in config.peers:
        loop.create_task(create_peer(receptor, *peer.split(":", 1), loop))
    ping_time = (((int(loop.time()) + 1) // PING_INTERVAL) + 1) * PING_INTERVAL
    loop.call_at(ping_time, loop.create_task, send_pings_and_reschedule(receptor, loop, ping_time))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.stop()


async def send_pings_and_reschedule(receptor, loop, ping_time):
    logger.debug(f'Scheduling mesh ping.')
    for node_id in receptor.router.get_nodes():
        await receptor.router.ping_node(node_id)
    loop.call_at(ping_time + PING_INTERVAL, 
                 loop.create_task, send_pings_and_reschedule(
                     receptor, loop, ping_time + PING_INTERVAL))
