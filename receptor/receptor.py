import os
import uuid
import asyncio
import logging

from .config import ReceptorConfig
from .router import MeshRouter
from .work import WorkManager
from .connection import Connection

logger = logging.getLogger(__name__)


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
