import asyncio
import logging
import os
import queue
from abc import abstractmethod, abstractproperty
from collections.abc import AsyncIterator

from ..messages.framed import FramedBuffer

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
    def send(self, q):
        pass


class BridgeQueue(queue.Queue):
    """
    BridgeQueue is a queue.Queue subclass intended to 'bridge' a real thread
    and a coroutine. Where the thread is the producer and the coroutine is
    the consumer.

    The queue implements the async iterator protocol for the consuming
    coroutine and exposes the normal queue.Queue for threads.

    Additionally, there is a sentinel value assigned to the queue that can be
    used to indicate when iteration should cease.
    """

    sentinel = object()

    async def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            try:
                item = self.get_nowait()
                if item is self.sentinel:
                    raise StopAsyncIteration
                else:
                    return item
            except queue.Empty:
                await asyncio.sleep(0.0)

    @classmethod
    def one(cls, item):
        """
        Constructs a BridgeQueue with the single provided item followed by
        the sentinel value.  This function does not block.
        """
        q = cls()
        q.put_nowait(item)
        q.put_nowait(q.sentinel)
        return q

    def read_from(self, fp, chunk_size=2 ** 12):
        """
        Reads from a file-like object in chunk_size blocks and puts the bytes
        into the queue.

        Once the file has been read completely, the queue's sentinel value is
        placed into the queue, signaling to the consumer that all data has
        been read.
        """
        chunk = fp.read(chunk_size)
        while chunk:
            self.put(chunk)
            chunk = fp.read(chunk_size)
        self.put(self.sentinel)


async def watch_queue(loop, conn, buf):
    try:
        logger.debug(f'Watching queue {str(conn)}')
        while not conn.closed:
            try:
                ident, fp = await asyncio.wait_for(buf.get(handle_only=True), 5.0)
                if not fp:
                    if conn is not None and not conn.closed:
                        await conn.close()
            except asyncio.TimeoutError:
                continue
            except Exception:
                logger.exception("watch_queue: error getting data from buffer")
                continue

            try:
                if conn.closed:
                    logger.debug('Message not sent: connection already closed')
                else:
                    q = BridgeQueue(maxsize=1)
                    await asyncio.gather(loop.run_in_executor(None, q.read_from, fp), conn.send(q))
            except Exception:
                logger.exception("watch_queue: error received trying to write")
                await buf.put_ident(ident)
                if conn is not None and not conn.closed:
                    return await conn.close()
                else:
                    return
            else:
                fp.close()
                try:
                    await loop.run_in_executor(None, os.remove, fp)
                except TypeError:
                    pass  # some messages aren't actually files
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
        msg = self.receptor._say_hi().serialize()
        await self.conn.send(BridgeQueue.one(msg))

    async def start_processing(self):
        await self.receptor.send_route_advertisement()
        logger.debug("starting normal loop")
        self.handle_task = self.loop.create_task(
            self.receptor.message_handler(self.buf)
        )
        out = self.receptor.buffer_mgr[self.remote_id]
        self.write_task = self.loop.create_task(watch_queue(self.loop, self.conn, out))
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
