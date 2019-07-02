import os
import uuid
import asyncio
import logging
import json

from .config import ReceptorConfig
from .router import MeshRouter
from .work import WorkManager
from . import exceptions
from .messages import envelope, directive

logger = logging.getLogger(__name__)

RECEPTOR_DIRECTIVE_NAMESPACE = 'receptor'


class Connection:
    def __init__(self, id_, protocol_obj, buffer_mgr, receptor):
        self.id_ = id_
        self.protocol_obj = protocol_obj
        self.buffer_mgr = buffer_mgr
        self.receptor = receptor

    def __str__(self):
        return f"<Connection {self.id_} {self.protocol_obj}>"

    async def handle_loop(self, buf):
        while True:
            for data in buf.get():
                if "cmd" in data and data["cmd"] == "ROUTE":
                    self.handle_route_advertisement(data)
                else:
                    await self.handle_message(data)
            await asyncio.sleep(.1)

    def handle_route_advertisement(self, data):
        for edge in data["edges"]:
            existing_edge = self.receptor.router.find_edge(edge[0], edge[1])
            if existing_edge and existing_edge[2] > edge[2]:
                self.receptor.router.update_node(edge[0], edge[1], edge[2])
            else:
                self.receptor.router.register_edge(*edge)
        self.send_route_advertisement(data["edges"], data["seen"])

    def send_route_advertisement(self, edges=None, seen=[]):
        edges = edges or self.receptor.router.get_edges()
        seen = set(seen)
        logger.debug("Emitting Route Advertisements, excluding {}".format(seen))
        destinations = set(self.receptor.connections) - seen
        seens = list(seen | destinations | {self.receptor.node_id})

        # TODO: This should be a broadcast call to the connection manager
        for target in destinations:
            buf = self.buffer_mgr.get_buffer_for_node(target)
            buf.push(json.dumps({
                "cmd": "ROUTE",
                "id": self.receptor.node_id,
                "edges": edges,
                "seen": seens
            }).encode("utf-8"))

    async def handle_message(self, msg):
        outer_env = envelope.OuterEnvelope(**msg)
        next_hop = self.receptor.router.next_hop(outer_env.recipient)
        if next_hop is None:
            await outer_env.deserialize_inner(self.receptor)
            if outer_env.inner_obj.message_type == 'directive':
                namespace, _ = outer_env.inner_obj.directive.split(':', 1)
                if namespace == RECEPTOR_DIRECTIVE_NAMESPACE:
                    await directive.control(self.receptor.router, outer_env.inner_obj)
                else:
                    # other namespace/work directives
                    await self.receptor.work_manager.handle(outer_env.inner_obj)
            elif outer_env.inner_obj.message_type == 'response':
                in_response_to = outer_env.inner_obj.in_response_to
                if in_response_to in self.receptor.router.response_registry:
                    logger.info(f'Handling response to {in_response_to} with callback.')
                    for connection in self.receptor.controller_connections:
                        connection.emit_response(outer_env.inner_obj)
                else:
                    logger.warning(f'Received response to {in_response_to} but no record of sent message.')
            else:
                raise exceptions.UnknownMessageType(
                    f'Unknown message type: {outer_env.inner_obj.message_type}')
        else:
            await self.receptor.router.forward(outer_env, next_hop)


class Receptor:
    def __init__(self, config=None, node_id=None, router_cls=None,
                 work_manager_cls=None):
        self.config = config or ReceptorConfig()
        self.node_id = node_id or self.config.receptor.node_id or self._find_node_id()
        self.router = (router_cls or MeshRouter)(self)
        self.work_manager = (work_manager_cls or WorkManager)(self)
        self.connections = dict()
        self.controller_connections = []
        self.stop = False

    def _find_node_id(self):
        if 'RECEPTOR_NODE_ID' in os.environ:
            return os.environ['RECEPTOR_NODE_ID']

        node_id = uuid.uuid4()
        if os.path.exists(os.path.join(os.getcwd(), 'Pipfile')):
            with open(os.path.join(os.getcwd(), '.env'), 'w+') as ofs:
                ofs.write(f'\nRECEPTOR_NODE_ID={node_id}\n')
        return str(node_id)

    def update_connections(self, connection):
        self.router.register_edge(connection.id_, self.node_id, 1)
        if connection.id_ in self.connections:
            self.connections[connection.id_].append(connection)
        else:
            self.connections[connection.id_] = [connection]

    def add_connection(self, id_, protocol_obj):
        buffer_mgr = self.config.components.buffer_manager
        conn = Connection(id_, protocol_obj, buffer_mgr, self)
        self.update_connections(conn)
        return conn

    def remove_connection(self, conn):
        notify_protocols = []
        for connection_node in self.connections:
            if conn in self.connections[connection_node]:
                logger.info("Removing connection {} for node {}".format(conn, connection_node))
                self.connections[connection_node].remove(conn)
                self.router.update_node(self.node_id, connection_node, 100)
                self.router.debug_router()
            notify_protocols += self.connections[connection_node]
        # TODO: Broadcast update, set timer for full expiration
        for active_protocol in notify_protocols:
            active_protocol.send_route_advertisement(self.router.get_edges())

    async def shutdown_handler(self):
        while True:
            if self.stop:
                return
            await asyncio.sleep(1)
