import asyncio
import logging
import json
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

    async def message_handler(self, buf):
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
