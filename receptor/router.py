import logging
logger = logging.getLogger(__name__)

from collections import defaultdict
import heapq
import random

from receptor import get_node_id

async def forward(outer_envelope, next_hop):
    """
    Forward a message on to the next hop closer to its destination
    """
    raise NotImplementedError()

def next_hop(recipient):
    """
    Return the node ID of the next hop for routing a message to the
    given recipient. If the current node is the recipient, then return
    None.
    """
    return router.find_shortest_path(recipient)[-2]

async def send(outer_envelope):
    """
    Send a new message with the given outer envelope.
    """
    raise NotImplementedError()

class MeshRouter:
    _nodes = set()
    _edges = set()

    def node_is_known(self, node_id):
        return node_id in self._nodes
    
    def register_edge(self, left, right, cost):
        self._nodes.add(left, right)
        self._edges.add(
            (
                left if left < right else right,
                right if left < right else left,
                cost
            )
        )

    def find_shortest_path(self, to_node_id):
        """Implementation of Dijkstra algorithm"""
        cost_map = defaultdict(list)
        for left, right, cost in self._edges:
            cost_map[left].append((cost, right))
            cost_map[right].append((cost, left))

        heap, seen, mins = [(0, get_node_id(), [])], set(), {get_node_id(): 0}
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
    
router = MeshRouter()
