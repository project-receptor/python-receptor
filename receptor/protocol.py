import asyncio
import logging
import json
from .handler import handle_msg
from .router import router
from receptor import get_node_id, config
from collections import deque

logger = logging.getLogger(__name__)

DELIM = b"\x1b[K"
SIZEB = b"\x1b[%dD"


async def create_peer(host, port, loop):
    while True:
        try:
            await loop.create_connection(lambda: BasicClientProtocol(loop), host, port)
            break
        except Exception:
            logger.exception("Connection Refused: {}:{}".format(host, port))
            await asyncio.sleep(5)


async def watch_queue(node, transport):
    buffer_mgr = config.components.buffer_manager
    buffer_obj = buffer_mgr.get_buffer_for_node(node)
    while True:
        if transport.is_closing():
            break
        try:
            msg = buffer_obj.pop()
            transport.write(msg.serialize().encode('utf8') + DELIM)
        except IndexError:
            logger.debug(f'Buffer for {node} is empty.')
        except Exception as e:
            logger.exception("Error received trying to write to {}: {}".format(node, e))
            buffer_obj.push(msg)
            transport.close()
            break
        await asyncio.sleep(1)


def join_router(id_, edges):
    router.register_edge(id_, get_node_id(), 1)
    for edge in json.loads(edges):
        router.register_edge(*edge)


class DataBuffer:
    def __init__(self):
        self.q = deque()
        self._buf = b""

    def add(self, data):
        self._buf = self._buf + data
        *ready, self._buf = self._buf.rsplit(DELIM)
        for chunk in ready:
            self.q.append(chunk)

    def get(self):
        while self.q:
            yield self.q.popleft()


class BaseProtocol(asyncio.Protocol):
    def __init__(self, loop):
        self.loop = loop

    def connection_made(self, transport):
        self.peername = transport.get_extra_info('peername')
        self.transport = transport
        self.greeted = False
        self._buf = DataBuffer()

    def data_received(self, data):
        logger.debug(data)
        self._buf.add(data)
        for d in self._buf.get():
            if not self.greeted:
                logger.debug('Looking for handshake...')
                self.handle_handshake(d)
            else:
                logger.debug('Passing to task handler...')
                self.loop.create_task(handle_msg(d))

    def handle_handshake(self, data):
        data = data.decode("utf-8")
        cmd, id_, edges = data.split(":", 2)
        if cmd == "HI":
            self.handshake(id_, edges)
        else:
            logger.error("Handshake failed!")

    def handshake(self, id_, edges):
        self.greeted = True
        join_router(id_, edges)
        self.loop.create_task(watch_queue(id_, self.transport))

    def send_handshake(self):
        self.transport.write(f"HI:{get_node_id()}:{router.get_edges()}".encode("utf-8") + DELIM)


class BasicProtocol(BaseProtocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        logger.info('Connection from {}'.format(self.peername))

    def handshake(self, id_, edges):
        super().handshake(id_, edges)
        logger.debug("Received handshake from client with id %s, responding...", id_)
        self.send_handshake()


class BasicClientProtocol(BaseProtocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        logger.info("Connection to %s", self.peername)
        logger.debug("Sending handshake to server...")
        self.send_handshake()

    def connection_lost(self, exc):
        logger.info('Connection lost with the client...')
        info = self.transport.get_extra_info('peername')
        self.loop.create_task(create_peer(info[0], info[1], self.loop))

    def handshake(self, id_, edges):
        super().handshake(id_, edges)
        logger.debug("Received handshake from server with id %s", id_)
