import asyncio
import datetime
import functools
import logging
import time
import uuid

from .messages import envelope
from .stats import connected_peers_gauge

logger = logging.getLogger(__name__)

DELIM = b"\x1b[K"


class BaseProtocol(asyncio.Protocol):
    def __init__(self, receptor, loop):
        self.receptor = receptor
        self.loop = loop
        self.id = None
        self.meta = None

    def __str__(self):
        return f"<Connection {self.id} {self.transport}"

    async def watch_queue(self):
        '''
        Watches the buffer for this connection for messages delivered from other
        parts of Receptor (forwarded messages for example) for messages to send
        over the connection.
        '''
        buffer_mgr = self.receptor.config.components_buffer_manager
        buffer_obj = buffer_mgr.get_buffer_for_node(self.id, self.receptor)
        while not self.transport.is_closing():
            try:
                msg = await buffer_obj.get()
            except Exception:
                logger.exception("Unhandled error when fetch from buffer for %s", self.id)
                continue

            try:
                self.transport.write(msg)
            except Exception:
                logger.exception("Error received trying to write to %s", self.id)
                await buffer_obj.put(msg)
                self.transport.close()
                return

    def connection_made(self, transport):
        self.peername = transport.get_extra_info('peername')
        self.transport = transport
        connected_peers_gauge.inc()
        self.incoming_buffer = envelope.FramedBuffer(loop=self.loop)
        self.loop.create_task(self.wait_greeting())

    def connection_lost(self, exc):
        connected_peers_gauge.dec()
        self.receptor.remove_connection(self)

    def data_received(self, data):
        # TODO: The put() call can raise an exception which should trigger a
        # transport failure.
        self.loop.create_task(self.incoming_buffer.put(data))

    async def wait_greeting(self):
        '''
        Initialized when the connection is established to handle the greeting
        before transitioning to message processing.
        '''
        logger.debug('Looking for handshake...')
        data = await self.incoming_buffer.get()
        if data.header["cmd"] == "HI":
            self.handle_handshake(data.header)
        else:
            logger.error("Handshake failed!")
            self.transport.close()

    def handle_handshake(self, data):
        logger.debug("handle_handshake: %s", data)
        self.id = data["id"]
        self.meta = data.get("meta", {})
        self.receptor.add_connection(self)
        self.loop.create_task(self.watch_queue())
        self.loop.create_task(self.receptor.message_handler(self.incoming_buffer))

    def send_handshake(self):
        self.transport.write(self.receptor._say_hi().serialize())


class BasicProtocol(BaseProtocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        logger.info('Connection from {}'.format(self.peername))

    def handle_handshake(self, data):
        super().handle_handshake(data)
        logger.debug("Received handshake from client with id %s, responding...", data["id"])
        self.send_handshake()
        self.loop.create_task(self.receptor.send_route_advertisement())


async def create_peer(receptor, loop, host, port):
    while True:
        try:
            await loop.create_connection(
                lambda: BasicClientProtocol(receptor, loop), host, port, ssl=receptor.config.get_client_ssl_context())
            break
        except Exception:
            logger.exception("Connection Refused: {}:{}".format(host, port))
            await asyncio.sleep(5)


class BasicClientProtocol(BaseProtocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        logger.info("Connection to %s", self.peername)
        logger.debug("Sending handshake to server...")
        self.send_handshake()

    def connection_lost(self, exc):
        logger.info('Connection lost with the server...')
        super().connection_lost(exc)
        info = self.transport.get_extra_info('peername')
        self.loop.create_task(create_peer(self.receptor, self.loop, info[0], info[1]))

    def handle_handshake(self, data):
        super().handle_handshake(data)
        logger.debug("Received handshake from server with id %s", data["id"])
        self.loop.create_task(self.receptor.send_route_advertisement())
