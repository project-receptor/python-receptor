import argparse
import asyncio
import logging

from .protocol import BasicProtocol, BasicClientProtocol

logger = logging.getLogger(__name__)


async def create_peer(host, port):
    while True:
        try:
            loop = asyncio.get_event_loop()
            await loop.create_connection(BasicClientProtocol, host, port)
            break
        except Exception:
            print("Connection Refused: {}:{}".format(host, port))
            await asyncio.sleep(5)

def mainloop(listen, port, controller={}, peers=[]):
    loop = asyncio.get_event_loop()
    listener = loop.create_server(
        BasicProtocol,
        listen, port)
    loop.create_task(listener)
    for peer in peers:
        loop.create_task(create_peer(peer.split(":")[0], peer.split(":")[1]))
    print('Serving on {}'.format("{}:{}".format(listen, port)))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    loop.close()
