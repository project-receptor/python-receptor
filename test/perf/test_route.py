from receptor_affinity.mesh import Node
from receptor_affinity.mesh import Mesh
from receptor_affinity.utils import random_port
import time

import pytest


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
    random_mesh.validate_routes()


def test_add_remove_node(random_mesh):
    nodeX = Node("nodeX", connections=["controller"], stats_enable=True, stats_port=random_port())
    random_mesh.add_node(nodeX)
    nodeX.start()
    random_mesh.settle()
    assert nodeX.ping(1) != "Failed"
    random_mesh.settle()
    assert "nodeX" in str(random_mesh.nodes["controller"].get_routes())
    random_mesh.validate_routes()
    nodeX.stop()


def test_alternative_route(tree_mesh):
    nodeX = Node(
        "nodeX", connections=["node4", "node3"], stats_enable=True, stats_port=random_port()
    )
    tree_mesh.add_node(nodeX)
    nodeX.start()
    tree_mesh.settle()
    assert nodeX.ping(1) != "Failed"
    tree_mesh.settle()
    assert "nodeX" in str(tree_mesh.nodes["controller"].get_routes())
    tree_mesh.validate_routes()
    tree_mesh.nodes["node3"].stop()
    time.sleep(7)
    tree_mesh.settle()
    # TODO make ping return quicker if it can't ping then reenable to ensure node3 is dead
    # assert tree_mesh.nodes['node3'].ping() != "Failed"
    assert nodeX.ping(1) != "Failed"
    tree_mesh.nodes["node3"].start()
    tree_mesh.settle()
    tree_mesh.nodes["node4"].stop()
    time.sleep(7)
    assert nodeX.ping(1) != "Failed"
    nodeX.stop()
