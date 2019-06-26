import logging

import datetime
from collections import defaultdict
import heapq
import random
import uuid

from dateutil import parser
from .messages import envelope
from .exceptions import UnrouteableError

logger = logging.getLogger(__name__)


async def log_ping(response):
    pong_received = datetime.datetime.utcnow()
    ping_sent, ping_received = response.raw_payload.split('|')
    ping_time = parser.parse(ping_received) - parser.parse(ping_sent)
    pong_time = pong_received - parser.parse(ping_received)
    logger.info(f'Ping report for {response.sender}: '
                f'ping={ping_time.total_seconds()}s; '
                f'pong={pong_time.total_seconds()}s')


class MeshRouter:
    _nodes = set()
    _edges = set()
    response_registry = dict()

    def __init__(self, receptor):
        self.receptor = receptor
        self.node_id = receptor.node_id

    def debug_router(self):
        logger.debug("Receptor Edges: {}".format(self._edges))
        if self.receptor.config.server.debug:
            fd = open("graph_{}.dot".format(self.receptor.node_id), "w")
            fd.write("graph {")
            for left, right, weight in self._edges:
                fd.write("{} -- {};".format(left, right))
            fd.write("}")
            fd.close()

    def node_is_known(self, node_id):
        return node_id in self._nodes or node_id == self.node_id

    def find_edge(self, left, right):
        node_actual = sorted([left, right])
        for edge in self._edges:
            if node_actual[0] == edge[0] and node_actual[1] == edge[1]:
                return edge
        return None

    def register_edge(self, left, right, cost):
        if left != self.node_id:
            self._nodes.add(left)
        if right != self.node_id:
            self._nodes.add(right)
        edge = self.update_node(left, right, cost)
        if not edge:
            self._edges.add((*sorted([left, right]), cost))
        self.debug_router()

    def update_node(self, left, right, cost):
        edge = self.find_edge(left, right)
        if edge:
            new_edge = (edge[0], edge[1], cost)
            self._edges.remove(edge)
            self._edges.add(new_edge)
            return edge
        return None

    def remove_node(self, node):
        edge = self.find_edge(self.node_id, node)
        if edge:
            self._edges.remove(edge)
            return edge
        return None

    def get_edges(self):
        """Returns set of edges"""
        return list(self._edges)
    
    def get_nodes(self):
        return self._nodes
    
    async def ping_node(self, node_id, callback=log_ping):
        logger.info(f'Sending ping to node {node_id}')
        now = datetime.datetime.utcnow().isoformat()
        ping_envelope = envelope.InnerEnvelope(
            receptor=self.receptor,
            message_id=str(uuid.uuid4()),
            sender=self.node_id,
            recipient=node_id,
            message_type='directive',
            timestamp=now,
            raw_payload=now,
            directive='receptor:ping',
            ttl=15
        )
        await self.send(ping_envelope, callback)

    def find_shortest_path(self, to_node_id):
        """Implementation of Dijkstra algorithm"""
        cost_map = defaultdict(list)
        for left, right, cost in self._edges:
            cost_map[left].append((cost, right))
            cost_map[right].append((cost, left))

        heap, seen, mins = [(0, self.node_id, [])], set(), {self.node_id: 0}
        while heap:
            (cost, vertex, path) = heapq.heappop(heap)
            if vertex not in seen:
                seen.add(vertex)
                path = [vertex] + path                
                if vertex == to_node_id:
                    logger.debug(f'Shortest path to {to_node_id} with cost {cost} is {path}')
                    return path
                cost_map_for_vertex = cost_map.get(vertex, ())
                random.shuffle(cost_map_for_vertex)
                for next_cost, next_vertex in cost_map.get(vertex, ()):
                    if next_vertex in seen:
                        continue
                    min_so_far = mins.get(next_vertex, None)
                    next_total_cost = cost + next_cost
                    if min_so_far is None or next_total_cost < min_so_far:
                        mins[next_vertex] = next_total_cost
                        heapq.heappush(heap, (next_total_cost, next_vertex, path))

    async def forward(self, outer_envelope, next_hop):
        """
        Forward a message on to the next hop closer to its destination
        """
        buffer_mgr = self.receptor.config.components.buffer_manager
        buffer_obj = buffer_mgr.get_buffer_for_node(next_hop)
        outer_envelope.route_list.append(self.node_id)
        logger.debug(f'Forwarding frame {outer_envelope.frame_id} to {next_hop}')
        buffer_obj.push(outer_envelope.serialize().encode("utf-8"))


    def next_hop(self, recipient):
        """
        Return the node ID of the next hop for routing a message to the
        given recipient. If the current node is the recipient or there is
        no path, then return None.
        """
        if recipient == self.node_id:
            return None
        path = self.find_shortest_path(recipient)
        if path:
            return path[-2]


    async def send(self, inner_envelope, expected_response=False):
        """
        Send a new message with the given outer envelope.
        """
        next_node_id = self.next_hop(inner_envelope.recipient)
        if not next_node_id:
            raise UnrouteableError(f'No route found to {inner_envelope.recipient}')
        signed = await inner_envelope.sign_and_serialize()
        outer_envelope = envelope.OuterEnvelope(
            frame_id=str(uuid.uuid4()),
            sender=self.node_id,
            recipient=inner_envelope.recipient,
            route_list=[self.node_id],
            inner=signed
        )
        logger.debug(f'Sending {inner_envelope.message_id} to {inner_envelope.recipient} via {next_node_id}')
        if expected_response and inner_envelope.message_type == 'directive':
            self.response_registry[inner_envelope.message_id] = dict(message_sent_time=inner_envelope.timestamp)
        await self.forward(outer_envelope, next_node_id)



