import asyncio
import copy
import json
import logging
import os
import time
import uuid

from . import exceptions
from .messages import directive, envelope
from .router import MeshRouter
from .stats import messages_received_counter
from .work import WorkManager

RECEPTOR_DIRECTIVE_NAMESPACE = 'receptor'
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
        self.buffer_mgr = self.config.components_buffer_manager
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
                buffer = self.buffer_mgr.get_buffer_for_node(connection["id"], self)
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

    def update_connections(self, protocol_obj):
        self.router.register_edge(protocol_obj.id, self.node_id, 1)
        if protocol_obj.id in self.connections:
            self.connections[protocol_obj.id].append(protocol_obj)
        else:
            self.connections[protocol_obj.id] = [protocol_obj]
        self.update_connection_manifest(protocol_obj.id)

    async def message_handler(self, buf):
        while True:
            data = await buf.get()
            if "cmd" in data and data["cmd"] == "ROUTE":
                await self.handle_route_advertisement(data)
            else:
                await self.handle_message(data)

    def add_connection(self, protocol_obj):
        self.update_connections(protocol_obj)

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
        protocol_obj.loop.create_task(self.send_route_advertisement(self.router.get_edges()))

    async def shutdown_handler(self):
        while True:
            if self.stop:
                return
            await asyncio.sleep(1)

    async def handle_route_advertisement(self, data):
        self.router.add_edges(data["edges"])
        await self.send_route_advertisement(data["edges"], data["seen"])

    async def send_route_advertisement(self, edges=None, seen=[]):
        edges = edges or self.router.get_edges()
        seen = set(seen)
        logger.debug("Emitting Route Advertisements, excluding {}".format(seen))
        destinations = set(self.connections) - seen
        seens = list(seen | destinations | {self.node_id})

        # TODO: This should be a broadcast call to the connection manager
        for target in destinations:
            buf = self.buffer_mgr.get_buffer_for_node(target, self)
            try:
                await buf.put(json.dumps({
                    "cmd": "ROUTE",
                    "id": self.node_id,
                    "capabilities": self.work_manager.get_capabilities(),
                    "groups": self.config.node_groups,
                    "edges": edges,
                    "seen": seens
                }).encode("utf-8"))
            except Exception as e:
                logger.exception("Error trying to broadcast routes and capabilities: {}".format(e))

    async def handle_directive(self, outer_env):
        try:
            namespace, _ = outer_env.inner_obj.directive.split(':', 1)
            if namespace == RECEPTOR_DIRECTIVE_NAMESPACE:
                await directive.control(self.router, outer_env.inner_obj)
            else:
                # other namespace/work directives
                await self.work_manager.handle(outer_env.inner_obj)
        except ValueError:
            logger.error("error in handle_message: Invalid directive -> '%s'. Sending failure response back." % (outer_env.inner_obj.directive,))
            err_resp = outer_env.inner_obj.make_response(
                receptor=self,
                recipient=outer_env.inner_obj.sender,
                payload="An invalid directive ('%s') was specified." % (outer_env.inner_obj.directive,),
                in_response_to=outer_env.inner_obj.message_id,
                serial=outer_env.inner_obj.serial + 1,
                ttl=15,
                code=1,
            )
            await self.router.send(err_resp)
        except Exception as e:
            logger.error("error in handle_message: '%s'. Sending failure response back." % (str(e),))
            err_resp = outer_env.inner_obj.make_response(
                receptor=self,
                recipient=outer_env.inner_obj.sender,
                payload=str(e),
                in_response_to=outer_env.inner_obj.message_id,
                serial=outer_env.inner_obj.serial + 1,
                ttl=15,
                code=1,
            )
            await self.router.send(err_resp)

    async def handle_response(self, outer_env):
        in_response_to = outer_env.inner_obj.in_response_to
        if in_response_to in self.router.response_registry:
            logger.info(f'Handling response to {in_response_to} with callback.')
            for connection in self.controller_connections:
                connection.emit_response(outer_env.inner_obj)
        else:
            logger.warning(f'Received response to {in_response_to} but no record of sent message.')

    async def handle_message(self, msg):
        handlers = dict(
            directive=self.handle_directive,
            response=self.handle_response,
        )
        messages_received_counter.inc()
        outer_env = envelope.OuterEnvelope(**msg)
        next_hop = self.router.next_hop(outer_env.recipient)
        if next_hop:
            return await self.router.forward(outer_env, next_hop)

        await outer_env.deserialize_inner(self)

        if outer_env.inner_obj.message_type not in handlers:
            raise exceptions.UnknownMessageType(
                f'Unknown message type: {outer_env.inner_obj.message_type}')

        await handlers[outer_env.inner_obj.message_type](outer_env)
