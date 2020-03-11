import functools
import asyncio
from urllib.parse import urlparse

from . import sock, ws

default_scheme_ports = {
    "rnp": 8888,
    "rnps": 8899,
    "ws": 80,
    "wss": 443,
}


def parse_peer(peer, role):
    if "://" not in peer:
        peer = f"rnp://{peer}"
    if peer.startswith("receptor://"):
        peer = peer.replace("receptor", "rnp", 1)
    parsed_peer = urlparse(peer)
    if (parsed_peer.scheme not in default_scheme_ports) or \
            (role == 'server' and (parsed_peer.path or parsed_peer.params or parsed_peer.query or parsed_peer.fragment)):
        raise RuntimeError(f"Invalid Receptor peer specified: {peer}")

    return parsed_peer


class Manager:
    def __init__(self, factory, ssl_context_factory, loop=None):
        self.factory = factory
        self.ssl_context_factory = ssl_context_factory
        self.loop = loop or asyncio.get_event_loop()

    def get_listener(self, listen_url):
        service = parse_peer(listen_url, 'server')
        ssl_context = self.ssl_context_factory("server") if service.scheme in ("rnps", "wss") else None
        if service.scheme in ("rnp", "rnps"):
            return asyncio.start_server(
                functools.partial(sock.serve, factory=self.factory),
                host=service.hostname,
                port=service.port or default_scheme_ports[service.scheme],
                ssl=ssl_context,
            )
        elif service.scheme in ("ws", "wss"):
            return self.loop.create_server(
                ws.app(self.factory).make_handler(),
                service.hostname,
                service.port or default_scheme_ports[service.scheme],
                ssl=ssl_context,
            )
        else:
            raise RuntimeError(f"Unknown URL scheme {service.scheme}")

    def get_peer(self, peer, reconnect=True, ws_extra_headers=None):
        service = parse_peer(peer, 'client')
        ssl_context = self.ssl_context_factory("client") if service.scheme in ("rnps", "wss") else None
        if service.scheme in ("rnp", "rnps"):
            return self.loop.create_task(sock.connect(service.hostname, service.port, self.factory,
                                         self.loop, ssl_context, reconnect))
        elif service.scheme in ("ws", "wss"):
            return self.loop.create_task(ws.connect(peer, self.factory, self.loop,
                                         ssl_context, reconnect, ws_extra_headers))
        else:
            raise RuntimeError(f"Unknown URL scheme {service.scheme}")
