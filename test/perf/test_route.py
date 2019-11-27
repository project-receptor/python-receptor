from test.perf.affinity import Node
from test.perf.affinity import Topology

import pytest
from wait_for import wait_for, TimedOutError


@pytest.fixture(scope="function")
def random_topology():
    topo = Topology.load_topology_from_file("test/perf/topology-random.yaml")
    try:
        topo.start(wait=True)
        yield topo
    except TimedOutError:
        pass
    finally:
        topo.stop()


@pytest.fixture(scope="function")
def tree_topology():
    topo = Topology.load_topology_from_file("test/perf/topology-tree.yaml")
    try:
        topo.start(wait=True)
        yield topo
    except TimedOutError:
        pass
    finally:
        topo.stop()


def test_default_routes_validate(random_topology):
    assert random_topology.validate_all_node_routes()


def test_add_remove_node(random_topology):
    nodeX = Node("nodeX", connections=["controller"])
    random_topology.add_node(nodeX)
    nodeX.start()
    wait_for(random_topology.validate_all_node_routes, num_sec=30)
    assert nodeX.ping(1) != "Failed"
    assert "nodeX" in random_topology.nodes["controller"].get_debug_dot()
    assert random_topology.validate_all_node_routes()


def test_alternative_route(tree_topology):
    nodeX = Node("nodeX", connections=["node4", "node3"])
    tree_topology.add_node(nodeX)
    nodeX.start()
    wait_for(tree_topology.validate_all_node_routes, num_sec=30)
    assert nodeX.ping(1) != "Failed"
    assert "nodeX" in tree_topology.nodes["controller"].get_debug_dot()
    assert tree_topology.validate_all_node_routes()
    tree_topology.nodes["node3"].stop()
    # TODO make ping return quicker if it can't ping then reenable to ensure node3 is dead
    # assert tree_topology.nodes['node3'].ping() != "Failed"
    assert nodeX.ping(1) != "Failed"
    tree_topology.nodes["node3"].start()
    wait_for(tree_topology.validate_all_node_routes, num_sec=30)
    tree_topology.nodes["node4"].stop()
    assert nodeX.ping(1) != "Failed"
