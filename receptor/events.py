import asyncio
import logging

from .protocol import BasicProtocol, create_peer
from .router import router

logger = logging.getLogger(__name__)

PING_INTERVAL = 15

def mainloop(config):
    loop = asyncio.get_event_loop()
    if not config.server.server_disable:
        listener = loop.create_server(
            BasicProtocol,
            config.server.address, config.server.port)
        loop.create_task(listener)
        logger.info('Serving on {}'.format("{}:{}".format(config.server.address,
                                                          config.server.port)))
    for peer in config.peers:
        loop.create_task(create_peer(peer.split(":")[0], peer.split(":")[1]))
    ping_time = (((int(loop.time()) + 1) // PING_INTERVAL) + 1) * PING_INTERVAL
    loop.call_at(ping_time, send_pings_and_reschedule, loop, ping_time)
    logger.info('Serving on {}'.format("{}:{}".format(config.server.address,
                                                      config.server.port)))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.stop()

async def send_pings_and_reschedule(loop, ping_time):
    for node_id in router.get_nodes():
        await router.ping_node(node_id)
    loop.call_at(ping_time + PING_INTERVAL, send_pings_and_reschedule,
                 loop, ping_time + PING_INTERVAL)
