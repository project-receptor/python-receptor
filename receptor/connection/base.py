import asyncio
import logging
import os
from abc import abstractmethod, abstractproperty
from collections.abc import AsyncIterator

from .. import fileio
from ..bridgequeue import BridgeQueue
from ..messages.framed import FramedBuffer
from ..stats import bytes_recv

logger = logging.getLogger(__name__)


def log_ssl_detail(transport):
    peername = transport.get_extra_info("peername")
    if transport.get_extra_info("ssl_object", None):
        cipher = transport.get_extra_info("cipher")
        peercert = transport.get_extra_info("peercert")
        logger.debug(
            f"""{cipher[1]} connection with {str(peername)} using cipher {cipher[0]}
                and certificate {str(peercert)}."""
        )
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
        self.outbound = None
        self.deferrer = fileio.Deferrer(loop=self.loop)

    def start_receiving(self):
        self.read_task = self.loop.create_task(self.receive())

    async def receive(self):
        try:
            async for msg in self.conn:
                if self.conn.closed:
                    break
                bytes_recv.inc(len(msg))
                await self.buf.put(msg)
        except ConnectionResetError:
            logger.debug("receive: other side closed the connection")
        except asyncio.CancelledError:
            logger.debug("receive: cancel request received")
        except Exception:
            logger.exception("receive")

    async def register(self):
        await self.receptor.update_connections(self.conn, id_=self.remote_id)

    async def unregister(self):
        await self.receptor.remove_connection(self.conn, id_=self.remote_id)
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
        await self.receptor.recalculate_and_send_routes_soon()
        logger.debug("starting normal loop")
        self.handle_task = self.loop.create_task(self.receptor.message_handler(self.buf))
        self.outbound = self.receptor.buffer_mgr[self.remote_id]
        self.write_task = self.loop.create_task(self.watch_queue())
        return await self.write_task

    async def close(self):
        if self.conn is not None and not self.conn.closed:
            return await self.conn.close()

    async def watch_queue(self):
        try:
            logger.debug(f"Watching queue {str(self.conn)}")
            while not self.conn.closed:
                try:
                    item = await asyncio.wait_for(self.outbound.get(), 5.0)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    logger.exception("watch_queue: error getting data from buffer")
                    continue
                else:
                    # TODO: I think we need to wait for this to finish before
                    # starting another .get
                    asyncio.ensure_future(self.drain_buf(item))

        except asyncio.CancelledError:
            logger.debug("watch_queue: cancel request received")
            await self.close()

    async def drain_buf(self, item):
        try:
            if self.conn.closed:
                logger.debug("Message not sent: connection already closed")
            else:
                q = BridgeQueue(maxsize=1)
                await asyncio.gather(
                    self.deferrer.defer(q.read_from, item["path"]), self.conn.send(q)
                )
        except Exception:
            # TODO: Break out these exceptions to deal with file problems
            # and network problem separately?
            logger.exception("watch_queue: error received trying to write")
            await self.outbound.put_ident(item)
            return await self.close()
        else:
            try:
                await self.deferrer.defer(os.remove, item["path"])
            except TypeError:
                logger.exception("failed to os.remove %s", item["path"])
                pass  # some messages aren't actually files

    async def _wait_handshake(self):
        logger.debug("waiting for HI")
        response = await self.buf.get()  # TODO: deal with timeout
        self.remote_id = response.header["id"]
        await self.register()
        await self.receptor.recalculate_and_send_routes_soon()

    async def client(self, transport):
        try:
            self.conn = transport
            self.start_receiving()
            await self.hello()
            await self._wait_handshake()
            await self.start_processing()
            logger.debug("normal exit")
        finally:
            await self.unregister()

    async def server(self, transport):
        try:
            self.conn = transport
            self.start_receiving()
            await self._wait_handshake()
            await self.hello()
            await self.start_processing()
        finally:
            await self.unregister()
