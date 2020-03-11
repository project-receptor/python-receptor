import asyncio
import json
import logging
import os
import time
import uuid

import pkg_resources

from . import exceptions
from .messages import directive, envelope
from .router import MeshRouter
from .stats import messages_received_counter, receptor_info
from .work import WorkManager

RECEPTOR_DIRECTIVE_NAMESPACE = 'receptor'
logger = logging.getLogger(__name__)


def is_peer_of(edge, node):
    """If the edge includes the given node, return the other node. Otherwise, return None."""
    if edge[0] == node:
        return edge[1]
    elif edge[1] == node:
        return edge[0]
    else:
        return None


def get_peers_of(edges, node):
    """Gets the peers of a given node"""
    peers = set()
    for edge in edges:
        peer = is_peer_of(edge, node)
        if peer:
            peers.add(peer)
    return peers


class Receptor:
    def __init__(self, config, node_id=None, router_cls=None,
                 work_manager_cls=None, response_queue=None):
        self.config = config
        self.node_id = node_id or self.config.default_node_id or self._find_node_id()
        self.router = (router_cls or MeshRouter)(self)
        self.work_manager = (work_manager_cls or WorkManager)(self)
        self.connections = dict()
        self.response_queue = response_queue
        self.base_path = os.path.join(self.config.default_data_dir, self.node_id)
        if not os.path.exists(self.base_path):
            os.makedirs(os.path.join(self.config.default_data_dir, self.node_id))
        self.connection_manifest_path = os.path.join(self.base_path, "connection_manifest")
        self.buffer_mgr = self.config.components_buffer_manager
        self.stop = False
        self.node_capabilities = {
                self.node_id: self.work_manager.get_capabilities()
                }
        try:
            receptor_dist = pkg_resources.get_distribution("receptor")
            receptor_version = receptor_dist.version
        except pkg_resources.DistributionNotFound:
            receptor_version = 'unknown'
        receptor_info.info(dict(node_id=self.node_id, receptor_version=receptor_version))

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
                await buffer.expire()
                if connection["last"] + 86400 < time.time():
                    self.remove_connection_manifest(connection["id"])
            await asyncio.sleep(600)

    def get_connection_manifest(self):
        if not os.path.exists(self.connection_manifest_path):
            return []
        try:
            with open(self.connection_manifest_path, "r") as fd:
                manifest = json.load(fd)
            return manifest
        except Exception as e:
            logger.warn("Failed to read connection manifest: {}".format(e))
            return []

    def write_connection_manifest(self, manifest):
        with open(self.connection_manifest_path, "w") as fd:
            json.dump(manifest, fd)

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

    def remove_connection_manifest(self, connection):
        logger.info("Expiring connection {}".format(connection))
        manifest = self.get_connection_manifest()
        if connection in manifest:
            manifest.remove(connection)
            self.write_connection_manifest(manifest)

    async def message_handler(self, buf):
        logger.debug("spawning message_handler")
        while True:
            try:
                data = await buf.get()
            except asyncio.CancelledError:
                logger.debug("message_handler: cancel request received")
                break
            except Exception:
                logger.exception("message_handler")
                break
            else:
                logger.debug("message_handler: %s", data)
                if "cmd" in data.header and data.header["cmd"] == "ROUTE":
                    await self.handle_route_advertisement(data.header)
                else:
                    asyncio.ensure_future(self.handle_message(data))

    def update_connections(self, protocol_obj, id_=None):
        if id_ is None:
            id_ = protocol_obj.id

        self.router.add_or_update_edges([(id_, self.node_id, 1)])
        if id_ in self.connections:
            self.connections[id_].append(protocol_obj)
        else:
            self.connections[id_] = [protocol_obj]
        self.update_connection_manifest(id_)

    def add_connection(self, protocol_obj):
        self.update_connections(protocol_obj)

    def remove_ephemeral(self, node):
        logger.debug(f"Removing ephemeral node {node}")
        if node in self.connections:
            self.remove_connection_manifest(node)
        if node in self.node_capabilities:
            del self.node_capabilities[node]
        self.router.remove_node(node)

    def remove_connection(self, protocol_obj, id_=None, loop=None):
        notify_connections = []
        for connection_node in self.connections:
            if protocol_obj in self.connections[connection_node]:
                logger.info("Removing connection {} for node {}".format(protocol_obj, connection_node))
                if self.is_ephemeral(connection_node):
                    self.connections[connection_node].remove(protocol_obj)
                    self.remove_ephemeral(connection_node)
                else:
                    self.connections[connection_node].remove(protocol_obj)
                    self.router.add_or_update_edges([(self.node_id, connection_node, 100)])
                    self.update_connection_manifest(connection_node)
            notify_connections += self.connections[connection_node]
        if loop is None:
            loop = getattr(protocol_obj, "loop", None)
        if loop is not None:
            loop.create_task(self.send_route_advertisement(self.router.get_edges()))

    def is_ephemeral(self, id_):
        return (id_ in self.node_capabilities and
                "ephemeral" in self.node_capabilities[id_] and
                self.node_capabilities[id_]["ephemeral"])

    def remove_connection_by_id(self, id_, loop=None):
        if id_ in self.connections:
            for protocol_obj in self.connections[id_]:
                self.remove_connection(protocol_obj, id_, loop)

    async def shutdown_handler(self):
        while True:
            if self.stop:
                return
            await asyncio.sleep(1)

    def _say_hi(self):
        return envelope.CommandMessage(header={
            "cmd": "HI",
            "id": self.node_id,
            "expire_time": time.time() + 10,
            "meta": dict(capabilities=self.work_manager.get_capabilities(),
                         groups=self.config.node_groups,
                         work=self.work_manager.get_work())
        })

    async def handle_route_advertisement(self, data):
        self.node_capabilities[data["id"]] = data["capabilities"]
        if "node_capabilities" in data:
            for node, caps in data["node_capabilities"].items():
                self.node_capabilities[node] = caps
        old_node_peers = get_peers_of(self.router.get_edges(), data["id"])
        new_node_peers = get_peers_of(data["edges"], data["id"])
        removed_peers = old_node_peers - new_node_peers
        for removed_peer in removed_peers:
            if self.is_ephemeral(removed_peer):
                self.remove_ephemeral(removed_peer)
        accepted_edges = list()
        for edge in data["edges"]:
            peer = is_peer_of(edge, self.node_id)
            if peer:
                if peer == data["id"]:
                    accepted_edges.append(edge)
                else:
                    logger.debug(f"Excluding edge {edge}")
            else:
                accepted_edges.append(edge)
        self.router.add_or_update_edges(accepted_edges)
        await self.send_route_advertisement(self.router.get_edges(), data["seen"])

    async def send_route_advertisement(self, edges=None, seen=None):
        edges = edges or self.router.get_edges()
        seen = set(seen) if seen else set()
        logger.debug("Emitting Route Advertisements, excluding {}".format(seen))
        destinations = set(self.connections) - seen
        seens = list(seen | destinations | {self.node_id})

        # TODO: This should be a broadcast call to the connection manager
        for target in destinations:
            buf = self.buffer_mgr.get_buffer_for_node(target, self)
            try:
                msg = envelope.CommandMessage(header={
                    "cmd": "ROUTE",
                    "id": self.node_id,
                    "capabilities": self.work_manager.get_capabilities(),
                    "node_capabilities": self.node_capabilities,
                    "groups": self.config.node_groups,
                    "edges": edges,
                    "seen": seens
                })
                await buf.put(msg.serialize())
            except Exception as e:
                logger.exception("Error trying to broadcast routes and capabilities: {}".format(e))

    async def handle_directive(self, inner):
        try:
            namespace, _ = inner.directive.split(':', 1)
            if namespace == RECEPTOR_DIRECTIVE_NAMESPACE:
                await directive.control(self.router, inner)
            else:
                # other namespace/work directives
                await self.work_manager.handle(inner)
        except ValueError:
            logger.error("error in handle_message: Invalid directive -> '%s'. Sending failure response back." % (inner.directive,))
            err_resp = inner.make_response(
                receptor=self,
                recipient=inner.sender,
                payload="An invalid directive ('%s') was specified." % (inner.directive,),
                in_response_to=inner.message_id,
                serial=inner.serial + 1,
                ttl=15,
                code=1,
            )
            await self.router.send(err_resp)
        except Exception as e:
            logger.error("error in handle_message: '%s'. Sending failure response back." % (str(e),))
            err_resp = inner.make_response(
                receptor=self,
                recipient=inner.sender,
                payload=str(e),
                in_response_to=inner.message_id,
                serial=inner.serial + 1,
                ttl=15,
                code=1,
            )
            await self.router.send(err_resp)

    async def handle_response(self, inner):
        in_response_to = inner.in_response_to
        if in_response_to in self.router.response_registry:
            logger.info(f'Handling response to {in_response_to} with callback.')
            await self.response_queue.put(inner)
        else:
            logger.warning(f'Received response to {in_response_to} but no record of sent message.')

    async def handle_message(self, msg):
        try:
            handlers = dict(
                directive=self.handle_directive,
                response=self.handle_response,
                eof=self.handle_response,
            )
            messages_received_counter.inc()

            if msg.header["recipient"] != self.node_id:
                next_hop = self.router.next_hop(msg.header["recipient"])
                return await self.router.forward(msg, next_hop)

            inner = await envelope.Inner.deserialize(self, msg.payload)

            if inner.message_type not in handlers:
                raise exceptions.UnknownMessageType(
                    f'Unknown message type: {inner.message_type}')

            await handlers[inner.message_type](inner)
        except Exception:
            logger.exception("handle_message")
