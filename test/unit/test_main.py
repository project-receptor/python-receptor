import pytest
import receptor
from receptor.config import ReceptorConfig
from receptor import Receptor
from receptor.node import mainloop
import socket
import asyncio
from mock import patch


@pytest.fixture
def receptor_config(unused_tcp_port):
    config = dict()
    config.setdefault('server', {})['port'] = unused_tcp_port
    return ReceptorConfig(cmdline_args=config)
    

@pytest.fixture
def receptor_service(receptor_config):
    return Receptor(config=receptor_config, node_id='A')


@pytest.fixture
def receptor_service_factory(unused_tcp_port_factory):
    def _receptor_service(node_name, peer_ports=[]):
        config = dict()
        config.setdefault('server', {})['port'] = unused_tcp_port_factory()
        config['peers'] = {'127.0.0.1:{}'.format(p): '' for p in peer_ports}
        receptor_config = ReceptorConfig(cmdline_args=config)
        return Receptor(config=receptor_config, node_id=node_name)
    return _receptor_service


async def connect_port(receptor_obj):
    n = 5
    while n:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1',receptor_obj.config.server.port))
        if result != 0:
            await asyncio.sleep(1)
            n = n - 1
            continue
        break
    receptor_obj.stop = True


async def wait_for_time(seconds):
    await asyncio.sleep(seconds)


@patch.object(receptor.protocol.BasicProtocol, 'connection_made')
def test_main_node(mock_connection_made, event_loop, receptor_service):
    event_loop.call_soon(event_loop.create_task, connect_port(receptor_service))
    mainloop(receptor=receptor_service, loop=event_loop)
    mock_connection_made.assert_called_once()


def test_peering(event_loop, receptor_service_factory):
    r1 = receptor_service_factory('A')
    r2 = receptor_service_factory('B', peer_ports=[r1.config.server.port])
    mainloop(receptor=r1, loop=event_loop, skip_run=True)
    mainloop(receptor=r2, loop=event_loop, skip_run=True)
    event_loop.run_until_complete(wait_for_time(10))
    assert r1.router.node_is_known('B')
    assert r2.router.node_is_known('A')
