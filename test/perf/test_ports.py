"""Test port binding logic."""
from uuid import uuid4

import psutil
import pytest
from receptor_affinity import utils
from receptor_affinity.exceptions import NodeUnavailableError
from receptor_affinity.mesh import Node


def test_invalid_listen_scheme():
    """Start a node, and give it a listen address with an invalid scheme.

    The node should fail to start. See `receptor #93`_.

    .. NOTE:: This test should be extended to check that a traceback isn't printed to stdout or
        stderr.

    .. _receptor #93: https://github.com/project-receptor/receptor/issues/93
    """
    node = Node(str(uuid4()), listen=f'harglebargle://127.0.0.1:{utils.random_port()}')
    with pytest.raises(NodeUnavailableError):
        node.start()


def test_no_port_given():
    """Start a node, and don't specify a port on which to listen.

    Assert that it listens on port 8888. Older versions of receptor would listen on a random port.
    See: `receptor #138`_.

    .. _receptor #138: https://github.com/project-receptor/receptor/issues/138
    """
    node = Node(str(uuid4()), listen=f'receptor://127.0.0.1')
    node.start()
    try:
        conns = psutil.Process(node.pid).connections()
        assert len(conns) == 1
        assert conns[0].laddr.port == 8888
    finally:
        node.stop()
