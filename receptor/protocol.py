import datetime
import asyncio
import logging
import json
import uuid
from collections import deque
from .messages import envelope

logger = logging.getLogger(__name__)

DELIM = b"\x1b[K"
SIZEB = b"\x1b[%dD"


class DataBuffer:
    def __init__(self, deserializer=json.loads):
        self.q = deque()
        self._buf = b""
        self.deserializer = deserializer

    def add(self, data):
        self._buf = self._buf + data
        *ready, self._buf = self._buf.rsplit(DELIM)
        self.q.extend(ready)

    def get(self):
        while self.q:
            yield self.deserializer(self.q.popleft())


class BaseProtocol(asyncio.Protocol):
    def __init__(self, receptor, loop):
        self.receptor = receptor
        self.loop = loop

    async def watch_queue(self, node, transport):
        buffer_mgr = self.receptor.config.components.buffer_manager
        buffer_obj = buffer_mgr.get_buffer_for_node(node)
        while not transport.is_closing():
            try:
                msg = buffer_obj.pop()
                transport.write(msg + DELIM)
            except IndexError:
                await asyncio.sleep(1)
            except Exception as e:
                logger.exception("Error received trying to write to {}: {}".format(node, e))
                buffer_obj.push(msg)
                transport.close()
                return

    def connection_made(self, transport):
        self.peername = transport.get_extra_info('peername')
        self.transport = transport
        self.greeted = False
        self._buf = DataBuffer()
        self.loop.create_task(self.consume())

    def connection_lost(self, exc):
        self.receptor.remove_connection(self)

    def data_received(self, data):
        logger.debug(data)
        self._buf.add(data)

    async def consume(self):
        while not self.greeted:
            logger.debug('Looking for handshake...')
            for data in self._buf.get():
                logger.debug(data)
                if data["cmd"] == "HI":
                    self.handle_handshake(data)
                    break
                else:
                    logger.error("Handshake failed!")
            await asyncio.sleep(.1)
        logger.debug("handshake complete, starting normal handle loop")
        self.loop.create_task(self.connection.handle_loop(self._buf))

    def handle_handshake(self, data):
        self.greeted = True
        self.connection = self.receptor.add_connection(data["id"], self)
        self.loop.create_task(self.watch_queue(data["id"], self.transport))
        self.loop.create_task(self.connection.handle_loop(self._buf))

    def send_handshake(self):
        msg = json.dumps({
            "cmd": "HI",
            "id": self.receptor.node_id,
        }).encode("utf-8")
        self.transport.write(msg + DELIM)


class BasicProtocol(BaseProtocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        logger.info('Connection from {}'.format(self.peername))

    def handle_handshake(self, data):
        super().handle_handshake(data)
        logger.debug("Received handshake from client with id %s, responding...", data["id"])
        self.send_handshake()
        self.connection.send_route_advertisement()


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
        self.connection.send_route_advertisement()


class BasicControllerProtocol(asyncio.Protocol):

    def __init__(self, receptor, loop):
        self.receptor = receptor
        self.loop = loop

    def connection_made(self, transport):
        self.transport = transport
        if self not in self.receptor.controller_connections:
            self.receptor.controller_connections.append(self)

    def connection_lost(self, exc):
        if self in self.receptor.controller_connections:
            self.receptor.controller_connections.remove(self)

    def emit_response(self, response):
        self.transport.write(json.dumps(dict(timestamp=response.timestamp,
                                             in_response_to=response.in_response_to,
                                             payload=response.raw_payload)).encode())

    def data_received(self, data):
        recipient, directive, payload = data.rstrip(DELIM).decode('utf8').split('\n', 2)
        message_id = str(uuid.uuid4())
        logger.info(f'{message_id}: Sending {directive} to {recipient}')
        sent_timestamp = datetime.datetime.utcnow()
        inner_env = envelope.InnerEnvelope(
            receptor=self.receptor,
            message_id=message_id,
            sender=self.receptor.node_id,
            recipient=recipient,
            message_type='directive',
            timestamp=sent_timestamp.isoformat(),
            raw_payload=payload,
            directive=directive
        )
        # TODO: Response expiration task?
        # TODO: Persistent registry?
        self.loop.create_task(self.receptor.router.send(inner_env,
                                                        expected_response=True))
