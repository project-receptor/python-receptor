from test.perf.affinity import Node
from test.perf.affinity import Topology
from test.perf.utils import random_port
import time

import pytest
from wait_for import wait_for


@pytest.fixture(scope="function")
def random_topology():
    topo = Topology.load_topology_from_file("test/perf/topology-random.yaml", use_diag_node=True)
    try:
        topo.start(wait=True)
        yield topo
    finally:
        topo.stop()


def test_websocket_reconnect(random_topology):
    nodeX = Node("nodeX", connections=["node1"], stats_enable=True, stats_port=random_port(),
                 listen=f"ws://127.0.0.1:{random_port()}")
    nodeY = Node("nodeY", connections=["nodeX"], stats_enable=True, stats_port=random_port(),
                 listen=f"ws://127.0.0.1:{random_port()}")
    random_topology.add_node(nodeX)
    random_topology.add_node(nodeY)
    nodeX.start()
    nodeY.start()
    wait_for(random_topology.validate_all_node_routes, delay=6, num_sec=30)
    assert nodeY.ping(1) != "Failed"
    nodeX.stop()
    time.sleep(7)
    assert nodeY.ping(1) == "Failed"
    nodeX.start()
    time.sleep(7)
    wait_for(random_topology.validate_all_node_routes, delay=6, num_sec=30)
    assert nodeY.ping(1) != "Failed"
    nodeY.stop()
    nodeX.stop()
