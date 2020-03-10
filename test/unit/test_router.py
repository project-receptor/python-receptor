import pytest
from receptor.router import MeshRouter

test_networks = [
    (
        [('a', 'b', 1), ('a', 'd', 1), ('a', 'f', 1), ('b', 'd', 1), ('b', 'c', 1),
         ('c', 'e', 1), ('c', 'h', 1), ('c', 'j', 1), ('e', 'f', 1), ('e', 'g', 1),
         ('e', 'h', 1), ('f', 'g', 1), ('g', 'h', 1), ('h', 'j', 1), ('h', 'k', 1),
         ('j', 'k', 1), ('j', 'm', 1), ('l', 'm', 1)],
        [('a', 'f', 'f'), ('a', 'm', 'b'), ('h', 'd', 'c')],
        [('a', {'b', 'd', 'f'}), ('f', {'a', 'e', 'g'}), ('j', {'c', 'h', 'k', 'm'})],
    ),
    (
        [('a', 'b', 1), ('b', 'c', 1), ('c', 'd', 1), ('d', 'e', 1), ('e', 'f', 1)],
        [('a', 'f', 'b'), ('c', 'a', 'b'), ('f', 'c', 'e')],
        [('a', {'b'}), ('f', {'e'}), ('c', {'b', 'd'})],
    ),
]


@pytest.mark.parametrize("edges, expected_next_hops, expected_neighbors", test_networks)
def test_next_hop(edges, expected_next_hops, expected_neighbors):
    for node_id, remote, enh in expected_next_hops:
        r = MeshRouter(node_id=node_id)
        r.add_or_update_edges(edges)
        assert r.next_hop(remote) == enh


@pytest.mark.parametrize("edges, expected_next_hops, expected_neighbors", test_networks)
def test_neighbors(edges, expected_next_hops, expected_neighbors):
    r = MeshRouter(node_id=edges[0][0])
    r.add_or_update_edges(edges)
    for node_id, neighbors in expected_neighbors:
        assert r.get_neighbors(node_id) == neighbors
