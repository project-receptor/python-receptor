import asyncio
import logging
from abc import abstractmethod, abstractproperty
from collections.abc import AsyncIterator

from ..messages.framed import FramedBuffer

logger = logging.getLogger(__name__)


class Transport(AsyncIterator):
    @abstractmethod
    async def close(self):
        pass

    @abstractproperty
    def closed(self):
        pass

    @abstractmethod
    async def send(self, bytes_):
        pass


async def watch_queue(conn, buf):
    try:
        while not conn.closed:
            try:
                msg = await asyncio.wait_for(buf.get(), 5.0)
                if not msg:
                    return await conn.close()
            except asyncio.TimeoutError:
                continue
            except Exception:
                logger.exception("watch_queue: error getting data from buffer")
                continue

            try:
                await conn.send(msg)
            except Exception:
                logger.exception("watch_queue: error received trying to write")
                await buf.put(msg)
                return await conn.close()
    except asyncio.CancelledError:
        logger.debug("watch_queue: cancel request received")
        await conn.close()


class Worker:
    def __init__(self, receptor, loop):
        self.receptor = receptor
        self.loop = loop
        self.conn = None
        self.buf = FramedBuffer(loop=self.loop)
        self.remote_id = None
        self.read_task = None
        self.handle_task = None
        self.write_task = None

    def start_receiving(self):
        self.read_task = self.loop.create_task(self.receive())

    async def receive(self):
        try:
            async for msg in self.conn:
                if self.conn.closed:
                    break
                await self.buf.put(msg)
        except asyncio.CancelledError:
            logger.debug("receive: cancel request received")
        except Exception:
            logger.exception("receive")

    def register(self):
        self.receptor.update_connections(self.conn, id_=self.remote_id)

    def unregister(self):
        self.receptor.remove_connection(self.conn, id_=self.remote_id, loop=self.loop)
        self._cancel(self.read_task)
        self._cancel(self.handle_task)
        self._cancel(self.write_task)

    def _cancel(self, task):
        if task:
            task.cancel()

    async def hello(self):
        logger.debug("sending HI")
        msg = self.receptor._say_hi().serialize()
        await self.conn.send(msg)

    async def start_processing(self):
        logger.debug("sending routes")
        await self.receptor.send_route_advertisement()
        logger.debug("starting normal loop")
        self.handle_task = self.loop.create_task(
            self.receptor.message_handler(self.buf)
        )
        out = self.receptor.buffer_mgr.get_buffer_for_node(
            self.remote_id, self.receptor
        )
        self.write_task = self.loop.create_task(watch_queue(self.conn, out))
        return await self.write_task

    async def _wait_handshake(self):
        logger.debug("waiting for HI")
        response = await self.buf.get()  # TODO: deal with timeout
        self.remote_id = response.header["id"]
        self.register()

    async def client(self, transport):
        try:
            self.conn = transport
            self.start_receiving()
            await self.hello()
            await self._wait_handshake()
            await self.start_processing()
            logger.debug("normal exit")
        finally:
            self.unregister()

    async def server(self, transport):
        try:
            self.conn = transport
            self.start_receiving()
            await self._wait_handshake()
            await self.hello()
            await self.start_processing()
        finally:
            self.unregister()
