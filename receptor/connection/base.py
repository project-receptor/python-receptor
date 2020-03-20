import asyncio
import logging
import os
from abc import abstractmethod, abstractproperty
from collections.abc import AsyncIterator

from ..bridgequeue import BridgeQueue
from ..messages.framed import FramedBuffer

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

    async def register(self):
        await self.receptor.update_connections(self.conn, id_=self.remote_id)

    async def unregister(self):
        await self.receptor.remove_connection(self.conn, id_=self.remote_id, loop=self.loop)
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
                    ident, fp = await asyncio.wait_for(self.outbound.get(handle_only=True), 5.0)
                    if not fp:
                        await self.close()
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    logger.exception("watch_queue: error getting data from buffer")
                    continue
                else:
                    asyncio.ensure_future(self.drain_buf(ident, fp))

        except asyncio.CancelledError:
            logger.debug("watch_queue: cancel request received")
            self.close()

    async def drain_buf(self, ident, fp):
        try:
            if self.conn.closed:
                logger.debug("Message not sent: connection already closed")
            else:
                q = BridgeQueue(maxsize=1)
                await asyncio.gather(
                    self.loop.run_in_executor(None, q.read_from, fp), self.conn.send(q)
                )
        except Exception:
            logger.exception("watch_queue: error received trying to write")
            await self.outbound.put_ident(ident)
            return await self.close()
        else:
            try:
                await self.loop.run_in_executor(None, os.remove, fp.name)
            except TypeError:
                logger.exception("failed to os.remove %s", fp)
                pass  # some messages aren't actually files
        finally:
            fp.close()

    async def _wait_handshake(self):
        logger.debug("waiting for HI")
        response = await self.buf.get()  # TODO: deal with timeout
        self.remote_id = response.header["id"]
        await self.register()

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
