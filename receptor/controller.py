import asyncio
import datetime
import logging
import uuid

from .ws import WSServer
from .protocol import BasicProtocol, create_peer
from .receptor import Receptor
from .messages import envelope

logger = logging.getLogger(__name__)


def connect_to_socket(socket_path):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)
    return sock


# TODO: track stats
class Controller:

    def __init__(self, config, loop=asyncio.get_event_loop(), queue=None):
        self.receptor = Receptor(config)
        self.loop = loop
        self.queue = queue
        if self.queue is None:
            self.queue = asyncio.Queue(loop=loop)
        self.receptor.response_queue = self.queue

    def enable_server(self, listen_address, listen_port):
        listener = self.loop.create_server(
            lambda: BasicProtocol(self.receptor, self.loop),
            listen_address, listen_port,
            ssl=self.receptor.config.get_server_ssl_context())
        logger.info("Serving on {}:{}".format(listen_address, listen_port))
        # TODO: Enable stats?
        self.loop.create_task(listener)

    def enable_websocket_server(self, listen_address, listen_port):
        listener = self.loop.create_server(
            WSServer(self.receptor, self.loop).app().make_handler(),
            listen_address, listen_port,
            ssl=self.receptor.config.get_server_ssl_context())
        logger.info("Server ws on {}:{}".format(listen_address, listen_port))
        self.loop.create_task(listener)

    async def add_peer(self, peer):
        # NOTE: Not signing or serializing
        logger.info("Connecting to peer {}".format(peer))
        await self.loop.create_task(create_peer(self.receptor, self.loop,
                                                *peer.strip().split(":", 1)))

    async def recv(self):
        inner = await self.receptor.response_queue.get()
        return inner.raw_payload

    async def send(self, message):
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
        await self.receptor.router.send(inner_env, expected_response=True)

    async def ping(self, destination):
        await self.receptor.router.ping_node(destination)

    def run(self, coro=None):
        try:
            if coro is None:
                coro = self.receptor.shutdown_handler
            self.loop.run_until_complete(coro())
        except KeyboardInterrupt:
            pass
        finally:
            self.loop.stop()
