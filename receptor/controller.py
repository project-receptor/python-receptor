import asyncio
import datetime
import logging
import uuid

from .receptor import Receptor
from .messages import envelope
from .connection.base import Worker
from .connection.manager import Manager

logger = logging.getLogger(__name__)


class Controller:

    def __init__(self, config, loop=asyncio.get_event_loop(), queue=None):
        self.receptor = Receptor(config)
        self.loop = loop
        self.connection_manager = Manager(
            lambda: Worker(self.receptor, loop),
            self.receptor.config.get_server_ssl_context(),
            loop
        )
        self.queue = queue
        if self.queue is None:
            self.queue = asyncio.Queue(loop=loop)
        self.receptor.response_queue = self.queue

    def enable_server(self, listen_urls):
        for url in listen_urls:
            listener = self.connection_manager.get_listener(url)
            logger.info("Serving on %s", url)
            self.loop.create_task(listener)

    def add_peer(self, peer):
        logger.info("Connecting to peer {}".format(peer))
        self.connection_manager.get_peer(peer)

    async def recv(self):
        inner = await self.receptor.response_queue.get()
        return inner.raw_payload

    async def send(self, message, expect_response=True):
        new_id = uuid.uuid4()
        inner_env = envelope.Inner(
            receptor=self.receptor,
            message_id=str(new_id),
            sender=self.receptor.node_id,
            recipient=message.recipient,
            message_type="directive",
            directive=message.directive,
            timestamp=datetime.datetime.utcnow().isoformat(),
            raw_payload=message.open().read(),
        )
        await self.receptor.router.send(inner_env, expected_response=expect_response)
        return new_id

    async def ping(self, destination, expected_response=True):
        return await self.receptor.router.ping_node(destination, expected_response)

    def run(self, app=None):
        try:
            if app is None:
                app = self.receptor.shutdown_handler
            self.loop.run_until_complete(app())
        except KeyboardInterrupt:
            pass
        finally:
            self.loop.stop()
