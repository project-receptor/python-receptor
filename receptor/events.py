import argparse
import asyncio
import logging

from .protocol import BasicProtocol

logger = logging.getLogger(__name__)

def mainloop():
    loop = asyncio.get_event_loop()
    coro = loop.create_server(
        BasicProtocol,
        None, 8888)
    server = loop.run_until_complete(coro)

    # Serve requests until Ctrl+C is pressed
    print('Serving on {}'.format(server.sockets[0].getsockname()))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
