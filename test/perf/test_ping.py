from test.perf.affinity import Topology
from wait_for import TimedOutError
import time
import pytest


@pytest.yield_fixture(
    scope="function",
    params=[
        "test/perf/topology-flat.yaml",
        "test/perf/topology-tree.yaml",
        "test/perf/topology-random.yaml",
    ],
    ids=["flat", "tree", "random"],
)
def topology(request):
    topo = Topology.load_topology_from_file(request.param, use_diag_node=True)
    try:
        topo.start(wait=True)
        yield topo
    except TimedOutError:
        raise
    finally:
        print(f"{time.time()} - Stopping current topo")
        print(topo.nodes['controller'])
        topo.stop()


def test_pings_perf(topology):
    results = topology.ping()
    topology.validate_ping_results(results)
