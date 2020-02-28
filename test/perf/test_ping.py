from receptor_affinity.mesh import Mesh
from wait_for import TimedOutError
import time
import pytest


@pytest.fixture(
    scope="function",
    params=[
        "test/perf/flat-mesh.yaml",
        "test/perf/tree-mesh.yaml",
        "test/perf/random-mesh.yaml",
    ],
    ids=["flat", "tree", "random"],
)
def mesh(request):
    mesh = Mesh.load_from_file(request.param, use_diag_node=True)
    try:
        mesh.start(wait=True)
        yield mesh
    except TimedOutError:
        raise
    finally:
        print(f"{time.time()} - Stopping current mesh")
        print(mesh.nodes['controller'])
        mesh.stop()


def test_pings_perf(mesh):
    results = mesh.ping()
    mesh.validate_ping_results(results)
