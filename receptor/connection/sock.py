import asyncio
import logging
from .base import Transport, log_ssl_detail

logger = logging.getLogger(__name__)


class RawSocket(Transport):
    def __init__(self, reader, writer, chunk_size=2 ** 8):
        self.reader = reader
        self.writer = writer
        self._closed = False
        self.chunk_size = chunk_size

    async def __anext__(self):
        bytes_ = await self.reader.read(self.chunk_size)
        if not bytes_:
            self.close()
        return bytes_

    @property
    def closed(self):
        return self._closed

    def close(self):
        self._closed = True
        self.writer.close()

    async def send(self, bytes_):
        self.writer.write(bytes_)
        await self.writer.drain()


async def connect(host, port, factory, loop=None, ssl=None, reconnect=True):
    if not loop:
        loop = asyncio.get_event_loop()

    worker = factory()
    try:
        r, w = await asyncio.open_connection(host, port, loop=loop, ssl=ssl)
        log_ssl_detail(w._transport)
        t = RawSocket(r, w)
        await worker.client(t)
    except Exception:
        logger.exception("sock.connect")
        if not reconnect:
            return False
    finally:
        if reconnect:
            await asyncio.sleep(5)
            logger.debug("sock.connect: reconnection")
            loop.create_task(connect(host, port, factory, loop))
    return True


async def serve(reader, writer, factory):
    log_ssl_detail(writer._transport)
    t = RawSocket(reader, writer)
    await factory().server(t)
