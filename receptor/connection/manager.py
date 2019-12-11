import functools
import asyncio
from urllib.parse import urlparse

from . import sock, ws


def parse_peer(peer):
    if "://" not in peer:
        peer = f"receptor://{peer}"
    return urlparse(peer)


class Manager:
    def __init__(self, factory, ssl_context, loop=None):
        self.factory = factory
        self.ssl_context = ssl_context
        self.loop = loop or asyncio.get_event_loop()

    def get_listener(self, listen_url):
        service = parse_peer(listen_url)
        if service.scheme == "receptor":
            return asyncio.start_server(
                functools.partial(sock.serve, factory=self.factory),
                host=service.hostname,
                port=service.port,
                ssl=self.ssl_context,
            )
        elif service.scheme in ("ws", "wss"):
            return self.loop.create_server(
                ws.app(self.factory).make_handler(),
                service.hostname,
                service.port,
                ssl=self.ssl_context,
            )

    def get_peer(self, peer):
        service = parse_peer(peer)
        if service.scheme == "receptor":
            self.loop.create_task(sock.connect(service.hostname, service.port, self.factory, self.loop))
        elif service.scheme in ("ws", "wss"):
            self.loop.create_task(ws.connect(peer, self.factory, self.loop))
