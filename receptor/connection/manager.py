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

        default_port = {
            "rnp": 8888,
            "rnps": 8899,
            "ws": 80,
            "wss": 443,
        }

        service = parse_peer(listen_url)
        ssl_context = self.ssl_context_factory("server") if service.scheme in ("rnps", "wss") else None
        if service.scheme in ("rnp", "rnps"):
            return asyncio.start_server(
                functools.partial(sock.serve, factory=self.factory),
                host=service.hostname,
                port=service.port or default_port[service.scheme],
                ssl=ssl_context,
            )
        elif service.scheme in ("ws", "wss"):
            return self.loop.create_server(
                ws.app(self.factory).make_handler(),
                service.hostname,
                service.port or default_port[service.scheme],
                ssl=ssl_context,
            )
        else:
            raise RuntimeError(f"Unknown URL scheme {service.scheme}")

    def get_peer(self, peer, reconnect=True, ws_extra_headers=None):
        service = parse_peer(peer)
        ssl_context = self.ssl_context_factory("client") if service.scheme in ("rnps", "wss") else None
        if service.scheme in ("rnp", "rnps"):
            return self.loop.create_task(sock.connect(service.hostname, service.port, self.factory,
                                         self.loop, ssl_context, reconnect))
        elif service.scheme in ("ws", "wss"):
            return self.loop.create_task(ws.connect(peer, self.factory, self.loop,
                                         ssl_context, reconnect, ws_extra_headers))
        else:
            raise RuntimeError(f"Unknown URL scheme {service.scheme}")
