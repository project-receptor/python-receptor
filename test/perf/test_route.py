from test.perf.affinity import Node
from test.perf.affinity import Topology
from test.perf.utils import random_port
import time

import pytest
from wait_for import wait_for, TimedOutError


@pytest.fixture(scope="function")
def random_topology():
    topo = Topology.load_topology_from_file("test/perf/topology-random.yaml", use_diag_node=True)
    try:
        topo.start(wait=True)
        yield topo
    finally:
        topo.stop()


@pytest.fixture(scope="function")
def tree_topology():
    topo = Topology.load_topology_from_file("test/perf/topology-tree.yaml", use_diag_node=True)
    try:
        topo.start(wait=True)
        yield topo
    finally:
        topo.stop()


def test_default_routes_validate(random_topology):
    assert random_topology.validate_all_node_routes()


def test_add_remove_node(random_topology):
    nodeX = Node("nodeX", connections=["controller"], stats_enable=True, stats_port=random_port())
    random_topology.add_node(nodeX)
    nodeX.start()
    wait_for(random_topology.validate_all_node_routes, delay=6, num_sec=30)
    assert nodeX.ping(1) != "Failed"
    wait_for(random_topology.validate_all_node_routes, delay=6, num_sec=30)
    assert "nodeX" in str(random_topology.nodes["controller"].get_routes())
    assert random_topology.validate_all_node_routes()
    nodeX.stop()


def test_alternative_route(tree_topology):
    nodeX = Node(
        "nodeX", connections=["node4", "node3"], stats_enable=True, stats_port=random_port()
    )
    tree_topology.add_node(nodeX)
    nodeX.start()
    wait_for(tree_topology.validate_all_node_routes, delay=6, num_sec=30)
    assert nodeX.ping(1) != "Failed"
    wait_for(tree_topology.validate_all_node_routes, delay=6, num_sec=30)
    assert "nodeX" in str(tree_topology.nodes["controller"].get_routes())
    assert tree_topology.validate_all_node_routes()
    tree_topology.nodes["node3"].stop()
    time.sleep(7)
    wait_for(tree_topology.validate_all_node_routes, num_sec=30)
    # TODO make ping return quicker if it can't ping then reenable to ensure node3 is dead
    # assert tree_topology.nodes['node3'].ping() != "Failed"
    assert nodeX.ping(1) != "Failed"
    tree_topology.nodes["node3"].start()
    wait_for(tree_topology.validate_all_node_routes, num_sec=30)
    tree_topology.nodes["node4"].stop()
    time.sleep(7)
    assert nodeX.ping(1) != "Failed"
    nodeX.stop()
