import logging
import functools
import aiohttp
import aiohttp.web
import asyncio

from . import Transport

logger = logging.getLogger(__name__)


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


async def connect(uri, factory, loop=None):
    if not loop:
        loop = asyncio.get_event_loop()

    worker = factory()
    try:
        async with aiohttp.ClientSession().ws_connect(uri) as ws:
            t = WebSocket(ws)
            await worker.client(t)
    except Exception:
        logger.exception("ws.connect")
    finally:
        await asyncio.sleep(5)
        logger.debug("ws.connect: reconnecting")
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
