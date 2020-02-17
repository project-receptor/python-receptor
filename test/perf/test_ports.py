"""Test port binding logic."""
from uuid import uuid4

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
