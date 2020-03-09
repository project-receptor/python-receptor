import asyncio
import datetime
import logging
import uuid

from contextlib import suppress

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
            self.receptor.config.get_ssl_context,
            loop
        )
        self.queue = queue
        if self.queue is None:
            self.queue = asyncio.Queue(loop=loop)
        self.receptor.response_queue = self.queue

    async def shutdown_loop(self):
        tasks = [task for task in asyncio.Task.all_tasks()
                 if task is not asyncio.Task.current_task()]
        # Retrieve and throw away all exceptions that happen after
        # the decision to shut down was made.
        for task in tasks:
            task.cancel()
            with suppress(Exception):
                await task
        await asyncio.gather(*tasks)
        self.loop.stop()

    async def exit_on_exceptions_in(self, tasks):
        try:
            for task in tasks:
                await task
        except Exception as e:
            logger.exception(str(e))
            self.loop.create_task(self.shutdown_loop())

    def enable_server(self, listen_urls):
        tasks = list()
        for url in listen_urls:
            listener = self.connection_manager.get_listener(url)
            logger.info("Serving on %s", url)
            tasks.append(self.loop.create_task(listener))
        return tasks

    def add_peer(self, peer, ws_extra_headers=None):
        logger.info("Connecting to peer {}".format(peer))
        return self.connection_manager.get_peer(peer, reconnect=not self.receptor.config._is_ephemeral,
                                                ws_extra_headers=ws_extra_headers)

    async def recv(self):
        return await self.receptor.response_queue.get()

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
