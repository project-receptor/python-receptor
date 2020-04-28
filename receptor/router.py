import asyncio
import datetime
import heapq
import itertools
import logging
import sys
from collections import defaultdict

from .exceptions import ReceptorBufferError, UnrouteableError
from .messages.framed import FramedMessage
from .stats import route_counter, route_info

logger = logging.getLogger(__name__)


class PriorityQueue:

    REMOVED = "$$$%%%<removed-task>%%%$$$"

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
        raise KeyError("Pop from empty PriorityQueue")

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
            raise RuntimeError("Unknown node_id")
        self.routing_table = dict()
        route_info.info(dict(edges="()"))

    def node_is_known(self, node_id):
        return node_id in self._nodes or node_id == self.node_id

    def add_or_update_edges(self, edges, replace_all=False):
        """
        Adds a list of edges supplied as (node1, node2, cost) tuples.
        Already-existing edges have their cost updated.
        Supplying a cost of None removes the edge.
        """
        if replace_all:
            self._nodes = set()
            self._edges = dict()
            self._neighbors = defaultdict(set)
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

    def get_edge_keys(self):
        """Returns list of edge keys as sorted node-pair tuples"""
        return set(self._edges.keys())

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
            cost[node] = sys.maxsize  # poor man's infinity
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
        now = datetime.datetime.utcnow()
        logger.info(f"Sending ping to node {node_id}, timestamp={now}")
        message = FramedMessage(
            header=dict(
                sender=self.node_id, recipient=node_id, timestamp=now, directive="receptor:ping"
            )
        )
        return await self.send(message, expected_response)

    async def forward(self, msg, next_hop):
        """
        Forward a message on to the next hop closer to its destination
        """
        buffer_obj = self.receptor.buffer_mgr[next_hop]
        if "route_list" not in msg.header or msg.header["route_list"][-1] != self.node_id:
            msg.header["route_list"].append(self.node_id)
        logger.debug(f"Forwarding frame {msg.msg_id} to {next_hop}")
        try:
            route_counter.inc()
            await buffer_obj.put(msg)
        except ReceptorBufferError as e:
            logger.exception(
                "Receptor Buffer Write Error forwarding message to {}: {}".format(next_hop, e)
            )
            # TODO: Possible to find another route? This might be a hard failure
        except Exception as e:
            logger.exception("Error trying to forward message to {}: {}".format(next_hop, e))

    async def send(self, message, expected_response=False):
        """
        Send a new message with the given outer envelope.
        """
        recipient = message.header["recipient"]
        next_node_id = self.next_hop(recipient)
        if not next_node_id:
            # TODO: This probably needs to emit an error response
            raise UnrouteableError(f"No route found to {recipient}")

        # TODO: Not signing/serializing in order to finish buffered output work

        message.header.update({"sender": self.node_id, "route_list": [self.node_id]})
        logger.debug(f"Sending {message.msg_id} to {recipient} via {next_node_id}")
        if expected_response and "directive" in message.header:
            self.response_registry[message.msg_id] = dict(
                message_sent_time=message.header["timestamp"]
            )
        if next_node_id == self.node_id:
            asyncio.ensure_future(self.receptor.handle_message(message))
        else:
            await self.forward(message, next_node_id)
        return message.msg_id
