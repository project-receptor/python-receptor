import asyncio
import json
import logging
import os
import time
import uuid
import collections

import pkg_resources

from . import exceptions, fileio, stats
from .buffers.file import FileBufferManager
from .exceptions import ReceptorMessageError
from .messages import directive, framed
from .router import MeshRouter
from .work import WorkManager

RECEPTOR_DIRECTIVE_NAMESPACE = "receptor"
logger = logging.getLogger(__name__)


class Manifest:
    def __init__(self, path):
        self.path = path
        self.lock = asyncio.Lock()

    async def watch_expire(self, buffer_mgr):
        while True:
            async with self.lock:
                current_manifest = await self.get()
                to_remove = set()
                for connection in current_manifest:
                    buffer = buffer_mgr[connection["id"]]
                    await buffer.expire_all()
                    if connection["last"] + 86400 < time.time():
                        to_remove.add(connection["id"])
                if to_remove:
                    await self.write([c for c in current_manifest if c["id"] not in to_remove])
            await asyncio.sleep(600)

    async def get(self):
        if not os.path.exists(self.path):
            return []
        try:
            data = await fileio.read(self.path, "r")
            return json.loads(data)
        except Exception as e:
            logger.warn("Failed to read connection manifest: %s", e)
            logger.exception("damn")
            return []

    async def write(self, manifest):
        await fileio.write(self.path, json.dumps(manifest), mode="w")

    async def update(self, connection):
        async with self.lock:
            manifest = await self.get()
            found = False
            for node in manifest:
                if node["id"] == connection:
                    node["last"] = time.time()
                    found = True
                    break
            if not found:
                manifest.append(dict(id=connection, last=time.time()))
            await self.write(manifest)

    async def remove(self, connection):
        async with self.lock:
            logger.info("Expiring connection %s", connection)
            current = await self.get()
            manifest = [m for m in current if m["id"] != connection]
            await self.write(manifest)


class Receptor:
    """ Owns all connections and maintains adding and removing them. """

    def __init__(
        self, config, node_id=None, router_cls=None, work_manager_cls=None, response_queue=None
    ):
        self.config = config
        self.node_id = node_id or self.config.default_node_id or self._find_node_id()
        self.router = (router_cls or MeshRouter)(self)
        self.route_sender_task = None
        self.route_send_time = time.time()
        self.last_sent_seq = None
        self.route_adv_seen = dict()
        self.work_manager = (work_manager_cls or WorkManager)(self)
        self.connections = dict()
        self.response_queue = response_queue
        self.base_path = os.path.join(self.config.default_data_dir, self.node_id)
        if not os.path.exists(self.base_path):
            os.makedirs(os.path.join(self.config.default_data_dir, self.node_id))
        self.connection_manifest = Manifest(os.path.join(self.base_path, "connection_manifest"))
        path = os.path.join(os.path.expanduser(self.base_path))
        self.buffer_mgr = FileBufferManager(path)
        self.stop = False
        self.known_nodes = collections.defaultdict(
            lambda: dict(capabilities=dict(), sequence=0, seq_epoch=0.0, connections=dict())
        )
        self.known_nodes[self.node_id]["seq_epoch"] = time.time()
        self.known_nodes[self.node_id]["capabilities"] = self.work_manager.get_capabilities()
        try:
            receptor_dist = pkg_resources.get_distribution("receptor")
            receptor_version = receptor_dist.version
        except pkg_resources.DistributionNotFound:
            receptor_version = "unknown"
        stats.receptor_info.info(dict(node_id=self.node_id, receptor_version=receptor_version))

    def _find_node_id(self):
        if "RECEPTOR_NODE_ID" in os.environ:
            return os.environ["RECEPTOR_NODE_ID"]

        node_id = uuid.uuid4()
        if os.path.exists(os.path.join(os.getcwd(), "Pipfile")):
            with open(os.path.join(os.getcwd(), ".env"), "w+") as ofs:
                ofs.write(f"\nRECEPTOR_NODE_ID={node_id}\n")
        return str(node_id)

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
                if "cmd" in data.header and data.header["cmd"].startswith("ROUTE"):
                    await self.handle_route_advertisement(data.header)
                else:
                    asyncio.ensure_future(self.handle_message(data))

    async def update_connections(self, protocol_obj, id_=None):
        if id_ is None:
            id_ = protocol_obj.id

        routing_changed = False
        if id_ in self.connections:
            if protocol_obj not in self.connections[id_]:
                self.connections[id_].append(protocol_obj)
                routing_changed = True
        else:
            self.connections[id_] = [protocol_obj]
            routing_changed = True
        await self.connection_manifest.update(id_)
<<<<<<< HEAD
        if routing_changed:
            await self.recalculate_and_send_routes_soon()
=======
        stats.connected_peers_gauge.inc()
>>>>>>> 943b3d5... refactoring module extraction

    async def remove_ephemeral(self, node):
        logger.debug(f"Removing ephemeral node {node}")
        changed = False
        if node in self.connections:
            await self.connection_manifest.remove(node)
            changed = True
        if node in self.known_nodes:
            del self.known_nodes[node]
            changed = True
        if changed:
            await self.recalculate_and_send_routes_soon()

    async def remove_connection(self, protocol_obj, id_=None):
        routing_changed = False
        for connection_node in self.connections:
            if protocol_obj in self.connections[connection_node]:
                routing_changed = True
                logger.info(f"Removing connection for node {connection_node}")
                if self.is_ephemeral(connection_node):
                    self.connections[connection_node].remove(protocol_obj)
                    await self.remove_ephemeral(connection_node)
                else:
                    self.connections[connection_node].remove(protocol_obj)
                    await self.connection_manifest.update(connection_node)
<<<<<<< HEAD
        if routing_changed:
            await self.recalculate_and_send_routes_soon()
=======
                stats.connected_peers_gauge.dec()
            notify_connections += self.connections[connection_node]
        if loop is None:
            loop = getattr(protocol_obj, "loop", None)
        if loop is not None:
            loop.create_task(self.send_route_advertisement(self.router.get_edges()))
>>>>>>> 943b3d5... refactoring module extraction

    def is_ephemeral(self, id_):
        return (
            id_ in self.known_nodes
            and "ephemeral" in self.known_nodes[id_]["capabilities"]
            and self.known_nodes[id_]["capabilities"]["ephemeral"]
        )

    async def remove_connection_by_id(self, id_, loop=None):
        if id_ in self.connections:
            for protocol_obj in self.connections[id_]:
                await self.remove_connection(protocol_obj, id_)

    async def shutdown_handler(self):
        while True:
            if self.stop:
                return
            await asyncio.sleep(1)

    def _say_hi(self):
        return framed.FramedMessage(
            header={
                "cmd": "HI",
                "id": self.node_id,
                "expire_time": time.time() + 10,
                "meta": dict(
                    capabilities=self.work_manager.get_capabilities(),
                    groups=self.config.node_groups,
                    work=self.work_manager.get_work(),
                ),
            }
        )

    async def recalculate_routes(self):
        """Construct local routing table from source data"""
        edge_costs = dict()
        logger.debug("Constructing routing table")
        for node in self.connections:
            if self.connections[node]:
                edge_costs[tuple(sorted([self.node_id, node]))] = 1
        manifest = await self.connection_manifest.get()
        for node in manifest:
            node_key = tuple(sorted([self.node_id, node["id"]]))
            if node_key not in edge_costs:
                edge_costs[node_key] = 100
        for node in self.known_nodes:
            if node == self.node_id:
                continue
            for conn, cost in self.known_nodes[node]["connections"].items():
                node_key = tuple(sorted([node, conn]))
                if node_key not in edge_costs:
                    edge_costs[node_key] = cost
            pass
        new_edges = [(key[0], key[1], value) for key, value in edge_costs.items()]
        if new_edges == self.router.get_edges():
            logger.debug(f"   Routing not changed. Existing table: {self.router.get_edges()}")
            return False
        else:
            self.router.add_or_update_edges(new_edges, replace_all=True)
            logger.debug(f"   Routing updated. New table: {self.router.get_edges()}")
            return True

    async def send_routes(self):
        """Send routing update to connected peers"""
        route_adv_id = str(uuid.uuid4())
        seq = self.known_nodes[self.node_id]["sequence"] + 1
        self.known_nodes[self.node_id]["sequence"] = seq
        logger.debug(f"Sending route advertisement {route_adv_id} seq {seq}")
        self.last_sent_seq = seq

        advertised_connections = dict()
        for node1, node2, cost in self.router.get_edges():
            other_node = (
                node1 if node2 == self.node_id else node2 if node1 == self.node_id else None
            )
            if other_node:
                advertised_connections[other_node] = cost
        logger.debug(f"   Advertised connections: {advertised_connections}")

        for node_id in self.connections:
            if not self.connections[node_id]:
                continue
            buf = self.buffer_mgr[node_id]
            try:
                msg = framed.FramedMessage(
                    header={
                        "cmd": "ROUTE2",
                        "recipient": node_id,
                        "id": self.node_id,
                        "origin": self.node_id,
                        "route_adv_id": route_adv_id,
                        "connections": advertised_connections,
                        "seq_epoch": self.known_nodes[self.node_id]["seq_epoch"],
                        "sequence": seq,
                        "node_capabilities": {
                            node: value["capabilities"]
                            for (node, value) in self.known_nodes.items()
                        },
                    }
                )
                await buf.put(msg.serialize())
                logger.debug(f"   Sent to {node_id}")
            except Exception as e:
                logger.exception("Error trying to send route update: {}".format(e))

    async def route_send_check(self, force_send=False):
        while time.time() < self.route_send_time:
            await asyncio.sleep(self.route_send_time - time.time())
        self.route_sender_task = None
        routes_changed = await self.recalculate_routes()
        if (
            force_send
            or routes_changed
            or self.known_nodes[self.node_id]["sequence"] != self.last_sent_seq
        ):
            await self.send_routes()

    async def recalculate_and_send_routes_soon(self, force_send=False):
        self.route_send_time = time.time() + 0.1
        if not self.route_sender_task:
            self.route_sender_task = asyncio.ensure_future(self.route_send_check(force_send))

    async def handle_route_advertisement(self, data):

        # Sanity checks of the message
        if "origin" in data:
            origin = data["origin"]
        else:
            raise exceptions.UnknownMessageType("Malformed route advertisement: No origin")
        if (
            "cmd" not in data
            or "route_adv_id" not in data
            or "seq_epoch" not in data
            or "sequence" not in data
            or data["cmd"] != "ROUTE2"
        ):
            raise exceptions.UnknownMessageType(
                f"Unknown route advertisement protocol received from {origin}"
            )
        logger.debug(
            f"Route advertisement {data['route_adv_id']} seq {data['sequence']} "
            + f"received From {origin} via {data['id']}"
        )

        # Check if we received an update about ourselves
        if origin == self.node_id:
            logger.debug(f"Ignoring route advertisement {data['sequence']} from ourselves")
            return

        # Check that we have not seen this exact update before
        expire_time = time.time() - 600
        self.route_adv_seen = {
            raid: exp for (raid, exp) in self.route_adv_seen.items() if exp > expire_time
        }
        if data["route_adv_id"] in self.route_adv_seen:
            logger.debug(f"Ignoring already-seen route advertisement {data['route_adv_id']}")
            return
        self.route_adv_seen[data["route_adv_id"]] = time.time()

        # If this is the first time we've seen this node, advertise ourselves to it
        if origin not in self.known_nodes:
            await self.recalculate_and_send_routes_soon(force_send=True)

        # Check that the epoch and sequence epoch are not older than what we already have
        if origin in self.known_nodes and (
            self.known_nodes[origin]["seq_epoch"] > data["seq_epoch"]
            or self.known_nodes[origin]["sequence"] >= data["sequence"]
        ):
            logger.warn(
                f"Ignoring routing update {data['route_adv_id']} from {origin} "
                + f"epoch {data['seq_epoch']} seq {data['sequence']} because we already have "
                + f"epoch {self.known_nodes[origin]['seq_epoch']} "
                + f"seq {self.known_nodes[origin['sequence']]}"
            )
            return

        # TODO: don't just assume this is all correct
        if "node_capabilities" in data:
            for node, caps in data["node_capabilities"].items():
                self.known_nodes[node]["capabilities"] = caps

        # Remove any orphaned leaf nodes
        unreachable = set()
        for node in self.known_nodes:
            if node == self.node_id:
                continue
            if (
                len(self.known_nodes[node]["connections"]) == 1
                and origin in self.known_nodes[node]["connections"]
                and node not in data["connections"]
            ):
                unreachable.add(node)
        for node in unreachable:
            logger.debug(f"Removing orphaned node {node}")
            del self.known_nodes[node]

        # Update our own routing table based on the data we just received
        self.known_nodes[origin]["connections"] = data["connections"]
        self.known_nodes[origin]["seq_epoch"] = data["seq_epoch"]
        self.known_nodes[origin]["sequence"] = data["sequence"]
        await self.recalculate_routes()

        # Re-send the routing update to all our connections except the one it came in on
        for conn in self.connections:
            if conn == data["id"]:
                continue
            send_data = dict(data)
            buf = self.buffer_mgr[conn]
            try:
                send_data["id"] = self.node_id
                send_data["recipient"] = conn
                msg = framed.FramedMessage(header=send_data)
                await buf.put(msg.serialize())
            except Exception as e:
                logger.exception("Error trying to forward route broadcast: {}".format(e))

    async def handle_directive(self, msg):
        try:
            namespace, _ = msg.header["directive"].split(":", 1)
            logger.debug(f"directive namespace is {namespace}")
            if namespace == RECEPTOR_DIRECTIVE_NAMESPACE:
                await directive.control(self.router, msg)
            else:
                # TODO: other namespace/work directives
                await self.work_manager.handle(msg)
        except ReceptorMessageError as e:
            logger.error(f"Receptor Message Error '{e}''")
        except ValueError:
            logger.error(
                f"""error in handle_message: Invalid directive -> '{msg}'. Sending failure
                    response back."""
            )
            err_resp = framed.FramedMessage(
                header=dict(
                    recipient=msg.header["sender"],
                    in_response_to=msg.msg_ig,
                    serial=msg.header["serial"] + 1,
                    code=1,
                ),
                payload="An invalid directive ('{}') was specified.".format(
                    msg.header["directive"]
                ),
            )
            await self.router.send(err_resp)
        except Exception as e:
            logger.error("error in handle_message: '%s'. Sending failure response back.", str(e))
            err_resp = framed.FramedMessage(
                header=dict(
                    recipient=msg.header["sender"],
                    in_response_to=msg.msg_id,
                    serial=msg.header["serial"] + 1,
                    code=1,
                ),
                payload=f"{e}",
            )
            await self.router.send(err_resp)

    async def handle_response(self, msg):
        logger.debug("handle_response: %s", msg)
        in_response_to = msg.header["in_response_to"]
        if in_response_to in self.router.response_registry:
            logger.info(f"Handling response to {in_response_to} with callback.")
            await self.response_queue.put(msg)
        else:
            logger.warning(f"Received response to {in_response_to} but no record of sent message.")

    async def handle_message(self, msg):
        try:
            stats.messages_received_counter.inc()

            if msg.header["recipient"] != self.node_id:
                next_hop = self.router.next_hop(msg.header["recipient"])
                return await self.router.forward(msg, next_hop)

            if "in_response_to" in msg.header:
                await self.handle_response(msg)
            elif "directive" in msg.header:
                await self.handle_directive(msg)
            else:
                raise exceptions.UnknownMessageType(
                    f"Failed to determine message type for data: {msg}"
                )
        except Exception:
            logger.exception("handle_message")
