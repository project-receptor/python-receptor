import logging

import asyncio
import aiohttp
import aiohttp.web

from .messages.envelope import FramedBuffer

logger = logging.getLogger(__name__)


async def watch_queue(ws, buf):
    while not ws.closed:
        try:
            msg = await buf.get()
        except Exception:
            logger.exception("watch_queue: error getting data from buffer")
            continue

        try:
            await ws.send_bytes(msg)
        except Exception:
            logger.exception("watch_queue: error received trying to write")
            await buf.put(msg)
            return await ws.close()
    logger.debug("watch_queue: ws is now closed")


class WSBase:
    def __init__(self, receptor, loop):
        self.receptor = receptor
        self.loop = loop
        self.buf = FramedBuffer(loop=self.loop)
        self.remote_id = None

    async def receive(self, ws):
        try:
            async for msg in ws:
                await self.buf.put(msg.data)
        except Exception:
            logger.exception("receive")

    def register(self, ws):
        self.receptor.update_connections(ws, id_=self.remote_id)

    async def hello(self, ws):
        msg = self.receptor._say_hi().serialize()
        await ws.send_bytes(msg)

    async def start_processing(self, ws):
        self.loop.create_task(self.receptor.message_handler(self.buf))
        out = self.receptor.buffer_mgr.get_buffer_for_node(
            self.remote_id, self.receptor
        )
        return await watch_queue(ws, out)


class WSClient(WSBase):
    async def connect(self, uri):
        try:
            async with aiohttp.ClientSession().ws_connect(uri) as ws:

                logger.debug("connect: starting recv")
                recv_loop = self.loop.create_task(self.receive(ws))  # reader
                logger.debug("connect: sending HI")
                await self.hello(ws)
                logger.debug("connect: waiting for HI")
                response = await self.buf.get()  # TODO: deal with timeout
                self.remote_id = response.header["id"]
                self.register(ws)
                logger.debug("connect: sending routes")
                await self.receptor.send_route_advertisement()
                logger.debug("connect: starting normal loop")
                await self.start_processing(ws)
                logger.debug("connect: normal exit")
        except Exception:
            logger.exception("connect")
            logger.debug("connect: reconnecting")
            self.loop.create_task(self.connect(uri))


class WSServer(WSBase):
    async def serve(self, request):

        ws = aiohttp.web.WebSocketResponse()
        await ws.prepare(request)

        logger.debug("serve: starting recv")
        self.loop.create_task(self.receive(ws))  # reader
        logger.debug("serve: waiting for HI")
        response = await self.buf.get()  # TODO: deal with timeout
        self.remote_id = response.header["id"]
        self.register(ws)
        logger.debug("serve: sending HI")
        await self.hello(ws)
        logger.debug("serve: sending routes")
        await self.receptor.send_route_advertisement()
        logger.debug("serve: starting normal recv loop")
        await self.start_processing(ws)

    def app(self):
        app = aiohttp.web.Application()
        app.add_routes([aiohttp.web.get("/", self.serve)])
        return app
