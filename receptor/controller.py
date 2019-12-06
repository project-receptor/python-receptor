import asyncio
import datetime
import functools
import logging
import uuid
from urllib.parse import urlparse

from .protocol import BasicProtocol, create_peer
from .receptor import Receptor
from .messages import envelope
from . import connection
from .connection import ws, sock, Worker
from . import protocol

logger = logging.getLogger(__name__)


class Controller:

    def __init__(self, config, loop=asyncio.get_event_loop(), queue=None):
        self.receptor = Receptor(config)
        self.loop = loop
        self.queue = queue
        if self.queue is None:
            self.queue = asyncio.Queue(loop=loop)
        self.receptor.response_queue = self.queue

    def parse_peer(self, peer):
        if "://" not in peer:
            peer = f"receptor://{peer}"
        return urlparse(peer)

    def enable_server(self, listen_url):
        service = self.parse_peer(listen_url)
        cb = functools.partial(sock.serve, factory=factory)
        listener = asyncio.start_server(
            client_connected_cb,
            host=service.hostname,
            port=service.port,
            ssl=self.receptor.config.get_server_ssl_context())
        logger.info("Serving on {}:{}".format(service.hostname, service.port))
        self.loop.create_task(listener)

    def enable_websocket_server(self, listen_url):
        service = urlparse(listen_url)
        factory = lambda: Worker(receptor, loop)
        listener = self.loop.create_server(
            ws.app(factory).make_handler(),
            service.hostname, service.port,
            ssl=self.receptor.config.get_server_ssl_context())
        logger.info("Serving websockets on {}:{}".format(service.hostname, service.port))
        self.loop.create_task(listener)

    async def add_peer(self, peer):
        parsed = self.parse_peer(peer)
        if parsed.scheme == 'receptor':
            logger.info("Connecting to receptor peer {}".format(peer))
            await self.loop.create_task(create_peer(self.receptor, self.loop, parsed.hostname, parsed.port))
        elif parsed.scheme in ('ws', 'wss'):
            logger.info("Connecting to websocket peer {}".format(peer))
            await self.loop.create_task(WSClient(self.receptor, self.loop).connect(peer))

    async def recv(self):
        inner = await self.receptor.response_queue.get()
        return inner.raw_payload

    async def send(self, message, expect_response=True):
        inner_env = envelope.Inner(
            receptor=self.receptor,
            message_id=str(uuid.uuid4()),
            sender=self.receptor.node_id,
            recipient=message.recipient,
            message_type="directive",
            directive=message.directive,
            timestamp=datetime.datetime.utcnow().isoformat(),
            raw_payload=message.fd.read(),
        )
        await self.receptor.router.send(inner_env, expected_response=expect_response)

    async def ping(self, destination, expected_response=True):
        await self.receptor.router.ping_node(destination, expected_response)

    def run(self, app=None):
        try:
            if app is None:
                app = self.receptor.shutdown_handler
            self.loop.run_until_complete(app())
        except KeyboardInterrupt:
            pass
        finally:
            self.loop.stop()
