import asyncio
import logging
from . import Transport

logger = logging.getLogger(__name__)


class RawSocket(Transport):
    def __init__(self, reader, writer, chunk_size=2 ** 8):
        self.reader = reader
        self.writer = writer
        self._closed = False
        self.chunk_size = chunk_size

    async def __anext__(self):
        bytes_ = await self.reader.read(self.chunk_size)
        return bytes_

    @property
    def closed(self):
        return self._closed

    async def close(self):
        self._closed = True
        await self.writer.close()

    async def send(self, bytes_):
        self.writer.write(bytes_)
        await self.writer.drain()


async def connect(host, port, factory, loop=None):
    if not loop:
        loop = asyncio.get_event_loop()

    worker = factory()
    try:
        r, w = await asyncio.open_connection(host, port, loop=loop)
        t = RawSocket(r, w)
        await worker.client(t)
    except Exception:
        logger.exception("sock.connect")
    finally:
        await asyncio.sleep(5)
        logger.debug("sock.connect: reconnection")
        loop.create_task(connect(host, port, factory, loop))


async def serve(reader, writer, factory):
    t = RawSocket(reader, writer)
    await factory().server(t)
