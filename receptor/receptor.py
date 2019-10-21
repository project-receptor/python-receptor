import os
import json
import uuid
import time
import asyncio
import logging
import copy

from .router import MeshRouter
from .work import WorkManager
from .connection import Connection

logger = logging.getLogger(__name__)


class Receptor:
    def __init__(self, config, node_id=None, router_cls=None,
                 work_manager_cls=None):
        self.config = config
        self.node_id = node_id or self.config.default_node_id or self._find_node_id()
        self.router = (router_cls or MeshRouter)(self)
        self.work_manager = (work_manager_cls or WorkManager)(self)
        self.connections = dict()
        self.controller_connections = []
        self.base_path = os.path.join(self.config.default_data_dir, self.node_id)
        if not os.path.exists(self.base_path):
            os.makedirs(os.path.join(self.config.default_data_dir, self.node_id))
        self.connection_manifest_path = os.path.join(self.base_path, "connection_manifest")
        self.stop = False

    def _find_node_id(self):
        if 'RECEPTOR_NODE_ID' in os.environ:
            return os.environ['RECEPTOR_NODE_ID']

        node_id = uuid.uuid4()
        if os.path.exists(os.path.join(os.getcwd(), 'Pipfile')):
            with open(os.path.join(os.getcwd(), '.env'), 'w+') as ofs:
                ofs.write(f'\nRECEPTOR_NODE_ID={node_id}\n')
        return str(node_id)

    async def watch_expire(self):
        while True:
            current_manifest = self.get_connection_manifest()
            for connection in current_manifest:
                buffer = self.config.components_buffer_manager.get_buffer_for_node(connection["id"], self)
                for ident, message in buffer:
                    message_actual = json.loads(message)
                    if "expire_time" in message_actual and message_actual['expire_time'] < time.time():
                        buffer.read_message(ident, remove=True)
                        logger.info("Expiring message {}:{}".format(ident, connection["id"]))
                        # TODO: Do something with expired message
                if connection["last"] + 86400 < time.time():
                    logger.info("Expiring connection {}".format(connection["id"]))
                    write_manifest = copy.copy(current_manifest)
                    write_manifest.remove(connection)
                    self.write_connection_manifest(write_manifest)
            await asyncio.sleep(600)

    def get_connection_manifest(self):
        if not os.path.exists(self.connection_manifest_path):
            return []
        try:
            fd = open(self.connection_manifest_path, "r")
            manifest = json.load(fd)
            return manifest
        except Exception as e:
            logger.warn("Failed to read connection manifest: {}".format(e))
            return []

    def write_connection_manifest(self, manifest):
        fd = open(self.connection_manifest_path, "w")
        json.dump(manifest, fd)
        fd.close()

    def update_connection_manifest(self, connection):
        manifest = self.get_connection_manifest()
        found = False
        for node in manifest:
            if node["id"] == connection:
                node["last"] = time.time()
                found = True
                break
        if not found:
            manifest.append(dict(id=connection,
                            last=time.time()))
        self.write_connection_manifest(manifest)
                        
    def update_connections(self, connection):
        self.router.register_edge(connection.id_, self.node_id, 1)
        if connection.id_ in self.connections:
            self.connections[connection.id_].append(connection)
        else:
            self.connections[connection.id_] = [connection]
        self.update_connection_manifest(connection.id_)

    def add_connection(self, id_, meta, protocol_obj):
        buffer_mgr = self.config.components_buffer_manager
        conn = Connection(id_, meta, protocol_obj, buffer_mgr, self)
        self.update_connections(conn)
        return conn

    def remove_connection(self, protocol_obj):
        notify_connections = []
        for connection_node in self.connections:
            if protocol_obj in self.connections[connection_node]:
                logger.info("Removing connection {} for node {}".format(protocol_obj, connection_node))
                self.update_connection_manifest(connection_node)
                self.connections[connection_node].remove(protocol_obj)
                self.router.update_node(self.node_id, connection_node, 100)
                self.router.debug_router()
                self.update_connection_manifest(connection_node)
            notify_connections += self.connections[connection_node]
        for active_connection in notify_connections:
            active_connection.send_route_advertisement(self.router.get_edges())

    async def shutdown_handler(self):
        while True:
            if self.stop:
                return
            await asyncio.sleep(1)
