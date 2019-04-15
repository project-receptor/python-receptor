import pytest
from receptor.config import ReceptorConfig
from receptor import Receptor
from receptor.node import mainloop

@pytest.fixture
def receptor_service_object(unused_tcp_port):
    rc = ReceptorConfig()
    rc.server.port = unused_tcp_port
    r = Receptor(config=rc, node_id='A')
    return r


def test_main_node(event_loop, receptor_service_object):
    def stop_receptor():
        receptor_service_object.stop = True
    #event_loop.call_at(20, event_loop.create_task, stop_receptor())
    mainloop(receptor=receptor_service_object,
             loop=event_loop)