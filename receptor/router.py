import sys
import asyncio
import datetime
import heapq
import logging
import uuid
import itertools
from collections import defaultdict

from .exceptions import ReceptorBufferError, UnrouteableError
from .messages import envelope
from .stats import route_counter, route_info

logger = logging.getLogger(__name__)


class PriorityQueue:

    REMOVED = '$$$%%%<removed-task>%%%$$$'

    def __init__(self):
        self.heap = list()
        self.entry_finder = dict()
        self.counter = itertools.count()

    def add_with_priority(self, item, priority):
        """Adds an item to the queue, or changes the priority of an existing item."""
        if item in self.entry_finder:
            self.remove_item(item)
        count = next(self.counter)
        entry = [priority, count, item]
        self.entry_finder[item] = entry
        heapq.heappush(self.heap, entry)

    def remove_item(self, item):
        """Removes an item from the queue."""
        entry = self.entry_finder.pop(item)
        entry[-1] = self.REMOVED

    def pop_item(self):
        """Returns the item from the queue with the lowest sort order."""
        while self.heap:
            priority, count, item = heapq.heappop(self.heap)
            if item is not self.REMOVED:
                del self.entry_finder[item]
                return item
        raise KeyError('Pop from empty PriorityQueue')

    def is_empty(self):
        """Returns True if the queue is empty."""
        for entry in self.heap:
            if entry[-1] is not self.REMOVED:
                return False
        return True


class MeshRouter:

    def __init__(self, receptor=None, node_id=None):
        self._nodes = set()
        self._edges = dict()
        self._neighbors = defaultdict(set)
        self.response_registry = dict()
        self.receptor = receptor
        if node_id:
            self.node_id = node_id
        elif receptor:
            self.node_id = receptor.node_id
        else:
            raise RuntimeError('Unknown node_id')
        self.routing_table = dict()
        route_info.info(dict(edges="()"))

    def node_is_known(self, node_id):
        return node_id in self._nodes or node_id == self.node_id

    def add_or_update_edges(self, edges):
        """
        Adds a list of edges supplied as (node1, node2, cost) tuples.
        Already-existing edges have their cost updated.
        Supplying a cost of None removes the edge.
        """
        for left, right, cost in edges:
            edge_key = tuple(sorted([left, right]))
            if edge_key not in self._edges:
                self._neighbors[left].add(right)
                self._neighbors[right].add(left)
                for node in edge_key:
                    if node != self.node_id:
                        self._nodes.add(node)
                self._edges[edge_key] = cost
            elif cost is None:
                del self._edges[edge_key]
            else:
                self._edges[edge_key] = cost
        self.update_routing_table()
        route_info.info(dict(edges=str(set(self.get_edges()))))

    def remove_node(self, node):
        """Removes a node and its associated edges."""
        edge_keys = [ek for ek in self._edges.keys() if ek[0] == node or ek[1] == node]
        for ek in edge_keys:
            del self._edges[ek]
        if node in self._neighbors:
            for neighbor in self._neighbors[node]:
                if node in self._neighbors[neighbor]:
                    self._neighbors[neighbor].remove(node)
            del self._neighbors[node]
        if node in self._nodes:
            self._nodes.remove(node)
        route_info.info(dict(edges=str(set(self.get_edges()))))

    def get_edges(self):
        """Returns set of edges as a list of (node1, node2, cost) tuples."""
        return [(ek[0], ek[1], cost) for ek, cost in self._edges.items()]

    def get_nodes(self):
        """Returns the list of nodes known to the router."""
        return [node for node in self._nodes]

    def get_neighbors(self, node):
        """Returns the set of nodes which are neighbors of the given node."""
        return self._neighbors[node]

    def get_edge_cost(self, node1, node2):
        """Returns the cost of the edge between node1 and node2."""
        if node1 == node2:
            return 0
        node_key = tuple(sorted([node1, node2]))
        if node_key in self._edges:
            return self._edges[node_key]
        else:
            return None

    def update_routing_table(self):
        """Dijkstra's algorithm"""
        Q = PriorityQueue()
        Q.add_with_priority(self.node_id, 0)
        cost = {self.node_id: 0}
        prev = dict()

        for node in self._nodes:
            cost[node] = sys.maxsize   # poor man's infinity
            prev[node] = None
            Q.add_with_priority(node, cost[node])

        while not Q.is_empty():
            node = Q.pop_item()
            for neighbor in self.get_neighbors(node):
                path_cost = cost[node] + self.get_edge_cost(node, neighbor)
                if path_cost < cost[neighbor]:
                    cost[neighbor] = path_cost
                    prev[neighbor] = node
                    Q.add_with_priority(neighbor, path_cost)

        new_routing_table = dict()
        for dest in self._nodes:
            p = dest
            while prev[p] != self.node_id:
                p = prev[p]
            new_routing_table[dest] = (p, cost[dest])
        self.routing_table = new_routing_table

    def next_hop(self, recipient):
        """
        Return the node ID of the next hop for routing a message to the
        given recipient. If the current node is the recipient or there is
        no path, then return None.
        """
        if recipient == self.node_id:
            return self.node_id
        elif recipient in self.routing_table:
            return self.routing_table[recipient][0]
        else:
            return None

    async def ping_node(self, node_id, expected_response=True):
        logger.info(f'Sending ping to node {node_id}')
        now = datetime.datetime.utcnow().isoformat()
        ping_envelope = envelope.Inner(
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
        return await self.send(ping_envelope, expected_response)

    async def forward(self, msg, next_hop):
        """
        Forward a message on to the next hop closer to its destination
        """
        buffer_mgr = self.receptor.config.components_buffer_manager
        buffer_obj = buffer_mgr.get_buffer_for_node(next_hop, self.receptor)
        msg.header["route_list"].append(self.node_id)
        logger.debug(f'Forwarding frame {msg.msg_id} to {next_hop}')
        try:
            route_counter.inc()
            await buffer_obj.put(msg.serialize())
        except ReceptorBufferError as e:
            logger.exception("Receptor Buffer Write Error forwarding message to {}: {}".format(next_hop, e))
            # TODO: Possible to find another route? This might be a hard failure
        except Exception as e:
            logger.exception("Error trying to forward message to {}: {}".format(next_hop, e))

    async def send(self, inner_envelope, expected_response=False):
        """
        Send a new message with the given outer envelope.
        """
        next_node_id = self.next_hop(inner_envelope.recipient)
        if not next_node_id:
            # TODO: This probably needs to emit an error response
            raise UnrouteableError(f'No route found to {inner_envelope.recipient}')
        signed = await inner_envelope.sign_and_serialize()
        header = {
            "sender": self.node_id,
            "recipient": inner_envelope.recipient,
            "route_list": [self.node_id]
        }
        msg = envelope.FramedMessage(msg_id=uuid.uuid4().int, header=header, payload=signed)
        logger.debug(f'Sending {inner_envelope.message_id} to {inner_envelope.recipient} via {next_node_id}')
        if expected_response and inner_envelope.message_type == 'directive':
            self.response_registry[inner_envelope.message_id] = dict(message_sent_time=inner_envelope.timestamp)
        if next_node_id == self.node_id:
            asyncio.ensure_future(self.receptor.handle_message(msg))
        else:
            await self.forward(msg, next_node_id)
