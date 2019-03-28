import asyncio
import logging

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

    def data_received(self, data):
        message = data.decode()
        print('Data received: {!r}'.format(message))
        self.transport.write(data)


class BasicClientProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        print('Connection to {}'.format(peername))
        self.transport = transport

    def data_received(self, data):
        message = data.decode()
        print('Data received: {!r}'.format(message))

    def connection_lost(self, exc):
        msg = 'Connection lost with the client...'
        info = self.transport.get_extra_info('peername')
        loop = asyncio.get_event_loop()
        loop.create_task(create_peer(info[0], info[1]))
