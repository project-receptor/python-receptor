from receptor_affinity.mesh import Node
from receptor_affinity.mesh import Mesh
from receptor_affinity.utils import random_port
import time

import pytest
from wait_for import wait_for


@pytest.fixture(scope="function")
def random_mesh():
    mesh = Mesh.load_from_file("test/perf/random-mesh.yaml", use_diag_node=True)
    try:
        mesh.start(wait=True)
        yield mesh
    finally:
        mesh.stop()


@pytest.fixture(scope="function")
def tree_mesh():
    mesh = Mesh.load_from_file("test/perf/tree-mesh.yaml", use_diag_node=True)
    try:
        mesh.start(wait=True)
        yield mesh
    finally:
        mesh.stop()


def test_default_routes_validate(random_mesh):
    assert random_mesh.validate_all_node_routes()


def test_add_remove_node(random_mesh):
    nodeX = Node("nodeX", connections=["controller"], stats_enable=True, stats_port=random_port())
    random_mesh.add_node(nodeX)
    nodeX.start()
    wait_for(random_mesh.validate_all_node_routes, delay=6, num_sec=30)
    assert nodeX.ping(1) != "Failed"
    wait_for(random_mesh.validate_all_node_routes, delay=6, num_sec=30)
    assert "nodeX" in str(random_mesh.nodes["controller"].get_routes())
    assert random_mesh.validate_all_node_routes()
    nodeX.stop()


def test_alternative_route(tree_mesh):
    nodeX = Node(
        "nodeX", connections=["node4", "node3"], stats_enable=True, stats_port=random_port()
    )
    tree_mesh.add_node(nodeX)
    nodeX.start()
    wait_for(tree_mesh.validate_all_node_routes, delay=6, num_sec=30)
    assert nodeX.ping(1) != "Failed"
    wait_for(tree_mesh.validate_all_node_routes, delay=6, num_sec=30)
    assert "nodeX" in str(tree_mesh.nodes["controller"].get_routes())
    assert tree_mesh.validate_all_node_routes()
    tree_mesh.nodes["node3"].stop()
    time.sleep(7)
    wait_for(tree_mesh.validate_all_node_routes, num_sec=30)
    # TODO make ping return quicker if it can't ping then reenable to ensure node3 is dead
    # assert tree_mesh.nodes['node3'].ping() != "Failed"
    assert nodeX.ping(1) != "Failed"
    tree_mesh.nodes["node3"].start()
    wait_for(tree_mesh.validate_all_node_routes, num_sec=30)
    tree_mesh.nodes["node4"].stop()
    time.sleep(7)
    assert nodeX.ping(1) != "Failed"
    nodeX.stop()
