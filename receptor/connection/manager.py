import functools
import asyncio
from urllib.parse import urlparse

from . import sock, ws


def parse_peer(peer):
    if "://" not in peer:
        peer = f"rnp://{peer}"
    if peer.startswith("receptor://"):
        peer = peer.replace("receptor", "rnp", 1)
    return urlparse(peer)


class Manager:
    def __init__(self, factory, ssl_context_factory, loop=None):
        self.factory = factory
        self.ssl_context_factory = ssl_context_factory
        self.loop = loop or asyncio.get_event_loop()

    def get_listener(self, listen_url):
        service = parse_peer(listen_url)
        ssl_context = None if service.scheme in ("rnp", "ws") else self.ssl_context_factory('server')
        if service.scheme in ("rnp", "rnps"):
            return asyncio.start_server(
                functools.partial(sock.serve, factory=self.factory),
                host=service.hostname,
                port=service.port,
                ssl=ssl_context,
            )
        elif service.scheme in ("ws", "wss"):
            return self.loop.create_server(
                ws.app(self.factory).make_handler(),
                service.hostname,
                service.port,
                ssl=ssl_context,
            )

    def get_peer(self, peer, reconnect=True):
        service = parse_peer(peer)
        ssl_context = None if service.scheme in ("rnp", "ws") else self.ssl_context_factory('client')
        if service.scheme in ("rnp", "rnps"):
            return self.loop.create_task(sock.connect(service.hostname, service.port, self.factory,
                                         self.loop, ssl_context, reconnect))
        elif service.scheme in ("ws", "wss"):
            return self.loop.create_task(ws.connect(peer, self.factory, self.loop,
                                         ssl_context, reconnect))
