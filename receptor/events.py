import asyncio
import logging

from .protocol import BasicProtocol, create_peer

logger = logging.getLogger(__name__)


def mainloop(config):
    loop = asyncio.get_event_loop()
    listener = loop.create_server(
        BasicProtocol,
        config.server.address, config.server.port)
    loop.create_task(listener)
    for peer in config.peers:
        loop.create_task(create_peer(peer.split(":")[0], peer.split(":")[1]))
    logger.info('Serving on {}'.format("{}:{}".format(config.server.address,
                                                      config.server.port)))
    try:
        loop.run_forever()
    finally:
        loop.close()
