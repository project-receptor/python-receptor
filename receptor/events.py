import argparse
import asyncio
import logging

from .protocol import BasicProtocol, BasicClientProtocol

logger = logging.getLogger(__name__)

def mainloop(listen, port, controller={}, peers=[]):
    loop = asyncio.get_event_loop()
    listener = loop.create_server(
        BasicProtocol,
        listen, port)
    loop.create_task(listener)
    for peer in peers:
        p = loop.create_connection(BasicClientProtocol,
                                   peer.split(":")[0], peer.split(":")[1])
        loop.create_task(p)
    print('Serving on {}'.format("{}:{}".format(listen, port)))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    loop.close()
