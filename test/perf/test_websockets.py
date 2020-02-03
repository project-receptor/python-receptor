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


def test_websocket_reconnect(random_mesh):
    nodeX = Node("nodeX", connections=["node1"], stats_enable=True, stats_port=random_port(),
                 listen=f"ws://127.0.0.1:{random_port()}")
    nodeY = Node("nodeY", connections=["nodeX"], stats_enable=True, stats_port=random_port(),
                 listen=f"ws://127.0.0.1:{random_port()}")
    random_mesh.add_node(nodeX)
    random_mesh.add_node(nodeY)
    nodeX.start()
    nodeY.start()
    random_mesh.settle()
    assert nodeY.ping(1) != "Failed"
    nodeX.stop()
    time.sleep(7)
    assert nodeY.ping(1) == "Failed"
    nodeX.start()
    time.sleep(7)
    random_mesh.settle()
    assert nodeY.ping(1) != "Failed"
    nodeY.stop()
    nodeX.stop()
