import json
import logging
import time

import aiohttp

from .protocol import DataBuffer

logger = logging.getLogger(__name__)


async def watch_queue(sock, buf):
    while sock.open:
        try:
            msg = await buf.get()
        except Exception:
            logger.exception("Error getting data from buffer")
        
        try:
            sock.send(msg)
        except Exception:
            logger.exception("Error received trying to write")
            await buf.put(msg)
            return await sock.close()


class WSClient:
    def __init__(self, receptor, loop):
        self.receptor = receptor
        self.loop = loop

    async def connect(self, uri):
        async with aiohttp.ClientSession().ws_connect(uri) as sock:
            # handshake
            node_id = await self.handshake(sock)
            incoming_buffer = DataBuffer()
            self.loop.create_task(self.receive(sock, incoming_buffer)) # reader

            buf = self.receptor.buffer_mgr.get_buffer_for_node(node_id, self.receptor)
            self.loop.create_task(watch_queue(sock, buf)) # writer

        self.loop.create_task(self.connect(uri))


    async def handshake(self, sock):
        msg = json.dumps({
            "cmd": "HI",
            "id": self.receptor.node_id,
            "expire_time": time.time() + 10,
            "meta": {
                "capabilities": self.receptor.work_manager.get_capabilities(),
                "groups": self.receptor.config.node_groups,
                "work": self.receptor.work_manager.get_work(),
            }
        }).encode("utf-8")
        await sock.send_bytes(msg)
        response = await sock.receive().json()
        return response["id"]

    async def receive(self, sock, buf):
        self.loop.create_task(self.receptor.message_handler(buf))
        async for msg in sock.receive():
            buf.add(msg.data)


class WSServer:

    def __init__(self, receptor, loop):
        self.receptor = receptor
        self.loop = loop

    async def serve(self, request):

        ws = aiohttp.web.WebSocketResponse()
        await ws.prepare(request)

        handshake = await ws.receive().json()
        await ws.send_json({
            "cmd": "HI",
            "id": self.receptor.node_id,
            "expire_time": time.time() + 10,
            "meta": {
                "capabilities": self.receptor.work_manager.get_capabilities(),
                "groups": self.receptor.config.node_groups,
                "work": self.receptor.work_manager.get_work(),
            }
        })

        buf = self.receptor.buffer_mgr.get_buffer_for_node(handshake["id"], self.receptor)
        self.loop.create_task(watch_queue(ws, buf)) # writer

        incoming_buffer = DataBuffer()
        self.loop.create_task(self.receptor.message_handler(incoming_buffer))
        async for msg in ws:
            incoming_buffer.add(msg.data)
