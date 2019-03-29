import argparse
import asyncio
import logging

from .protocol import BasicProtocol, BasicClientProtocol, create_peer

logger = logging.getLogger(__name__)


def mainloop(listen, port, controller={}, peers=[]):
    loop = asyncio.get_event_loop()
    listener = loop.create_server(
        BasicProtocol,
        listen, port)
    loop.create_task(listener)
    for peer in peers:
        loop.create_task(create_peer(peer.split(":")[0], peer.split(":")[1]))
    logger.info('Serving on {}'.format("{}:{}".format(listen, port)))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    loop.close()
