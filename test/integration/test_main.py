import asyncio
import socket
from unittest.mock import patch

import pytest

import receptor
from receptor.config import ReceptorConfig
from receptor.receptor import Receptor


@pytest.fixture
def receptor_config(unused_tcp_port, tmpdir, type="node"):
    return ReceptorConfig(['--data-dir', tmpdir.strpath, type, '--listen', '127.0.0.1:'+str(unused_tcp_port)])


@pytest.fixture
def receptor_service(receptor_config):
    return Receptor(config=receptor_config, node_id='A')


@pytest.fixture
def receptor_service_factory(unused_tcp_port_factory, tmpdir):
    def _receptor_service(node_name, peer_ports=None, type="node"):
        if peer_ports is None:
            peer_ports = []
        peers = {'127.0.0.1:{}'.format(p): '' for p in peer_ports}
        peer_config = []
        for peer in peers:
            peer_config.extend(['--peer', peer])
        base_config = ['--node-id', node_name, '--data-dir', tmpdir.strpath, type, '--listen', '127.0.0.1'+str(unused_tcp_port_factory())]
        base_config.extend(peer_config)
        receptor_config = ReceptorConfig(base_config)
        return Receptor(receptor_config)
    return _receptor_service


async def connect_port(receptor_obj):
    n = 5
    while n:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        node, port = receptor_obj.config.node_listen[0].split(":")
        result = sock.connect_ex((node, int(port)))
        if result != 0:
            await asyncio.sleep(1)
            n = n - 1
            continue
        break
    receptor_obj.stop = True


async def wait_for_time(seconds):
    await asyncio.sleep(seconds)


@patch('receptor.connection.sock.serve')
def test_main_node(mock_sock, event_loop, receptor_config):
    c = receptor.Controller(receptor_config, loop=event_loop)
    event_loop.call_soon(event_loop.create_task, connect_port(c.receptor))
    c.enable_server(receptor_config.node_listen)
    c.run()
    mock_sock.assert_called_once()
