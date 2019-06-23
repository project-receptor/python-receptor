import datetime
import asyncio
import logging
import json
import uuid
from collections import deque

from . import exceptions
from .messages import envelope, directive

logger = logging.getLogger(__name__)

DELIM = b"\x1b[K"
SIZEB = b"\x1b[%dD"
RECEPTOR_DIRECTIVE_NAMESPACE = 'receptor'


class DataBuffer:
    def __init__(self):
        self.q = deque()
        self._buf = b""

    def add(self, data):
        self._buf = self._buf + data
        *ready, self._buf = self._buf.rsplit(DELIM)
        for chunk in ready:
            self.q.append(chunk)

    def get(self):
        while self.q:
            yield self.q.popleft()


class BaseProtocol(asyncio.Protocol):
    def __init__(self, receptor, loop):
        self.receptor = receptor
        self.loop = loop

    async def watch_queue(self, node, transport):
        buffer_mgr = self.receptor.config.components.buffer_manager
        buffer_obj = buffer_mgr.get_buffer_for_node(node)
        while True:
            if transport.is_closing():
                break
            try:
                msg = buffer_obj.pop()
                transport.write(msg.serialize().encode('utf8') + DELIM)
            except IndexError:
                await asyncio.sleep(1)
            except Exception as e:
                logger.exception("Error received trying to write to {}: {}".format(node, e))
                buffer_obj.push(msg)
                transport.close()
                break


    def join_router(self, id_, edges):
        self.receptor.router.register_edge(id_, self.receptor.node_id, 1)
        # TODO: Verify this isn't needed with route advertisements
        # for edge in json.loads(edges):
        #     self.receptor.router.register_edge(*edge)


    def connection_made(self, transport):
        self.peername = transport.get_extra_info('peername')
        self.transport = transport
        self.greeted = False
        self._buf = DataBuffer()

    def connection_lost(self, exc):
        self.receptor.remove_connection(self)

    def data_received(self, data):
        logger.debug(data)
        self._buf.add(data)
        for d in self._buf.get():
            if not self.greeted:
                logger.debug('Looking for handshake...')
                self.handle_handshake(d)
            elif d[:5] == b'ROUTE':
                logger.debug('Received Route Advertisement')
                self.handle_route_advertisement(d)
            else:
                logger.debug('Passing to task handler...')
                outer = envelope.OuterEnvelope.from_raw(d)
                self.loop.create_task(self.handle_msg(outer))

    def handle_handshake(self, data):
        data = data.decode("utf-8")
        cmd, id_, edges = data.split(";", 2)
        if cmd == "HI":
            self.handshake(id_, edges)
        else:
            logger.error("Handshake failed!")

    def handle_route_advertisement(self, data):
        data = data.decode("utf-8")
        cmd, id_, edges, seen = data.split(";", 3)
        edges_actual = json.loads(edges)
        seen_actual = json.loads(seen)
        for edge in edges_actual:
            existing_edge = self.receptor.router.find_edge(edge[0], edge[1])
            if existing_edge and existing_edge[2] > edge[2]:
                self.receptor.router.update_node(edge[0], edge[1], edge[2])
            else:
                self.receptor.router.register_edge(*edge)
        self.send_route_advertisement(edges, seen_actual)
    
    async def _handle_directive(self, obj):
        if obj.directive.namespace == RECEPTOR_DIRECTIVE_NAMESPACE:
            await directive.control(self.receptor.router, obj)
        else:
            # other namespace/work directives
            await self.receptor.work_manager.handle(obj)

    async def _handle_response(self, obj):
        if obj.in_response_to not in self.receptor.router.response_registry:
            logger.warning(f'Received response to {obj.in_response_to} but no record of sent message.')
            return

        logger.info(f'Handling response to {obj.in_response_to} with callback.')
        for connection in self.receptor.controller_connections:
            connection.emit_response(obj)

    handlers = {
        "directive": _handle_directive,
        "response": _handle_response,
    }

    async def handle_msg(self, msg):
        if await self.receptor.router.forward(msg):
            return

        obj = await msg.deserialize_inner(self.receptor)
        try:
            await self.handlers[obj.message_type](obj)
        except KeyError:
            # TODO: Nothing is going to catch this right now
            #       Should we respond to the caller with the error?
            raise exceptions.UnknownMessageType(
                f'Unknown message type: {obj.message_type}')


    def handshake(self, id_, edges):
        self.greeted = True
        self.join_router(id_, edges)
        self.receptor.add_connection(id_, self)
        self.loop.create_task(self.watch_queue(id_, self.transport))

    def send_route_advertisement(self, edges, exclude=[]):
        logger.debug("Emitting Route Advertisements, excluding {}".format(exclude))
        destinations = list(filter(lambda x: x not in exclude, self.receptor.connections.keys()))
        new_excludes = json.dumps(exclude + destinations + [self.receptor.node_id])
        for target in destinations:
            connection_list = self.receptor.connections[target]
            if connection_list:
                connection_list[0].transport.write(f"ROUTE;{self.receptor.node_id};{edges};{new_excludes}".encode("utf-8") + DELIM)

    def send_handshake(self):
        self.transport.write(f"HI;{self.receptor.node_id};{self.receptor.router.get_edges()}".encode("utf-8") + DELIM)


class BasicProtocol(BaseProtocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        logger.info('Connection from {}'.format(self.peername))

    def handshake(self, id_, edges):
        super().handshake(id_, edges)
        logger.debug("Received handshake from client with id %s, responding...", id_)
        self.send_handshake()
        self.send_route_advertisement(self.receptor.router.get_edges())


async def create_peer(receptor, loop, host, port):
    while True:
        try:
            await loop.create_connection(
                lambda: BasicClientProtocol(receptor, loop), host, port)
            break
        except Exception:
            logger.exception("Connection Refused: {}:{}".format(host, port))
            await asyncio.sleep(5)


class BasicClientProtocol(BaseProtocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        logger.info("Connection to %s", self.peername)
        logger.debug("Sending handshake to server...")
        self.send_handshake()

    def connection_lost(self, exc):
        logger.info('Connection lost with the server...')
        super().connection_lost(exc)
        info = self.transport.get_extra_info('peername')
        self.loop.create_task(create_peer(self.receptor, self.loop, info[0], info[1]))

    def handshake(self, id_, edges):
        super().handshake(id_, edges)
        logger.debug("Received handshake from server with id %s", id_)
        self.send_route_advertisement(self.receptor.router.get_edges())


class BasicControllerProtocol(asyncio.Protocol):

    def __init__(self, receptor, loop):
        self.receptor = receptor
        self.loop = loop

    def connection_made(self, transport):
        self.transport = transport
        if self not in self.receptor.controller_connections:
            self.receptor.controller_connections.append(self)

    def connection_lost(self, exc):
        if self in self.receptor.controller_connections:
            self.receptor.controller_connections.remove(self)

    def emit_response(self, response):
        self.transport.write(json.dumps(
            dict(timestamp=response.timestamp,
                 in_response_to=response.in_response_to,
                 payload=response.raw_payload)
        ).encode())

    def data_received(self, data):
        recipient, directive, payload = data.rstrip(DELIM).decode('utf8').split('\n', 2)
        message_id = str(uuid.uuid4())
        logger.info(f'{message_id}: Sending {directive} to {recipient}')
        sent_timestamp = datetime.datetime.utcnow()
        inner_env = envelope.InnerEnvelope(
            receptor=self.receptor,
            message_id=message_id,
            sender=self.receptor.node_id,
            recipient=recipient,
            message_type='directive',
            timestamp=sent_timestamp.isoformat(),
            raw_payload=payload,
            directive=directive
        )
        # TODO: Response expiration task?
        # TODO: Persistent registry?
        self.loop.create_task(self.receptor.router.send(inner_env,
                                                        expected_response=True))
