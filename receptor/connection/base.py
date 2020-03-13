import asyncio
import logging
from abc import abstractmethod, abstractproperty
from collections.abc import AsyncIterator

from ..messages.envelope import FramedBuffer

logger = logging.getLogger(__name__)


def log_ssl_detail(transport):
    peername = transport.get_extra_info('peername')
    if transport.get_extra_info('ssl_object', None):
        cipher = transport.get_extra_info('cipher')
        peercert = transport.get_extra_info('peercert')
        logger.debug(f"{cipher[1]} connection with {str(peername)} using cipher {cipher[0]} and certificate {str(peercert)}.")
    else:
        logger.debug(f"Unencrypted connection with {str(peername)}.")


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
        logger.debug(f'Watching queue {str(conn)}')
        while not conn.closed:
            try:
                msg = await asyncio.wait_for(buf.get(), 5.0)
                if not msg:
                    if conn is not None and not conn.closed:
                        await conn.close()
            except asyncio.TimeoutError:
                continue
            except Exception:
                logger.exception("watch_queue: error getting data from buffer")
                continue

            def _send_done(fut):
                if fut.exception():
                    logger.error("watch_queue: error received trying to write")
                    asyncio.ensure_future(buf.put(msg))
                    if conn is not None and not conn.closed:
                        asyncio.ensure_future(conn.close())

            if conn.closed:
                logger.debug('Message not sent: connection already closed')
            else:
                logger.debug(f'Sending message {str(msg)}')
                asyncio.ensure_future(conn.send(msg)).add_done_callback(_send_done)

    except asyncio.CancelledError:
        logger.debug("watch_queue: cancel request received")
        if conn is not None and not conn.closed:
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
