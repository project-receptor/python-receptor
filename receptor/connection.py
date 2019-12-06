import logging

import functools
import asyncio
import aiohttp
import aiohttp.web

from .messages.envelope import FramedBuffer

logger = logging.getLogger(__name__)


class Transport:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise NotImplementedError("subclasses should implement this")

    async def close(self):
        raise NotImplementedError("subclasses should implement this")

    @property
    def closed(self):
        raise NotImplementedError("subclasses should implement this")

    async def send(self, bytes_):
        raise NotImplementedError("subclasses should implement this")


class WebSocket(Transport):
    def __init__(self, ws):
        self.ws = ws

    async def __anext__(self):
        msg = await self.ws.__anext__()
        return msg.data

    async def close(self):
        return await self.ws.close()

    @property
    def closed(self):
        return self.ws.closed

    async def send(self, bytes_):
        await self.ws.send_bytes(bytes_)


async def watch_queue(conn, buf):
    while not conn.closed:
        try:
            msg = await asyncio.wait_for(buf.get(), 5.0)
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
    logger.debug("watch_queue: ws is now closed")


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
        logger.debug("starting recv")
        self.read_task = self.loop.create_task(self.receive())

    async def receive(self):
        try:
            async for msg in self.conn:
                await self.buf.put(msg)
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
        logger.debug("serve: waiting for HI")
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
            logger.debug("connect: normal exit")
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


async def connect(uri, factory, loop=None):
    if not loop:
        loop = asyncio.get_event_loop()

    worker = factory()
    try:
        async with aiohttp.ClientSession().ws_connect(uri) as ws:
            t = WebSocket(ws)
            await worker.client(t)
    except Exception:
        logger.exception("connect")
    finally:
        await asyncio.sleep(5)
        logger.debug("reconnecting")
        loop.create_task(connect(uri, factory=factory, loop=loop))


async def serve(request, factory):
    ws = aiohttp.web.WebSocketResponse()
    await ws.prepare(request)

    t = WebSocket(ws)
    await factory().server(t)


def app(factory):
    handler = functools.partial(serve, factory=factory)
    app = aiohttp.web.Application()
    app.add_routes([aiohttp.web.get("/", handler)])
    return app
