import asyncio
import logging
from .handler import handle_msg
from receptor import get_node_id

logger = logging.getLogger(__name__)


async def create_peer(host, port):
    while True:
        try:
            loop = asyncio.get_event_loop()
            await loop.create_connection(BasicClientProtocol, host, port)
            break
        except Exception:
            print("Connection Refused: {}:{}".format(host, port))
            await asyncio.sleep(5)


class BasicProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        print('Connection from {}'.format(peername))
        self.transport = transport
        self.greeted = False

    def data_received(self, data):
        logger.info(data)
        if not self.greeted:
            self.handshake(data)
        else:
            self.loop.create_task(handle_msg(data))
        # message = data.decode()
        # print('Data received: {!r}'.format(message))
        # self.transport.write(data)

    def handshake(self, data):
        cmd, id_ = data.split(b" ", 1)
        if cmd != b"HI":
            logger.error("Handshake failed!")
        else:
            self.greeted = True
            logger.debug("Received handshake from client with id %s, responding...", id_)
            self.transport.write(b"HI %s" % get_node_id().encode("utf-8"))
            # send routing updates


class BasicClientProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        print('Connection to {}'.format(peername))
        self.transport = transport
        self.greeted = False
        logger.debug("Sending handshake to server...")
        self.transport.write(b"HI %s" % get_node_id().encode("utf-8"))

    def data_received(self, data):
        logger.info(data)
        if not self.greeted:
            self.handshake(data)
        else:
            self.loop.create_task(handle_msg(data))
        # message = data.decode()
        # print('Data received: {!r}'.format(message))

    def connection_lost(self, exc):
        logger.info('Connection lost with the client...')
        info = self.transport.get_extra_info('peername')
        loop = asyncio.get_event_loop()
        loop.create_task(create_peer(info[0], info[1]))

    def handshake(self, data):
        cmd, id_ = data.split(b" ", 1)
        if cmd != b"HI":
            logger.error("Handshake failed!")
        else:
            logger.debug("Received handshake from server with id %s", id_)
            self.greeted = True
