import pytest
import os
import io
from tempfile import mkstemp
from receptor.messages.envelope import Message
from receptor.exceptions import ReceptorRuntimeError


@pytest.yield_fixture
def afile():
    f = mkstemp()
    yield f
    os.remove(f[1])


def test_message_file_handling(afile):
    os.write(afile[0], b"test")
    m = Message("receipient", "test")
    m.file(afile[1])
    assert m.open().read() == b"test"


def test_message_data_handling():
    m = Message("receipient", "test")
    m.data(b"test")
    assert m.open().read() == b"test"

    with pytest.raises(TypeError):
        m.data("test")
        assert m.open().read() == b"test"


def test_message_buffer_handling():
    m = Message("receipient", "test")
    i = io.BytesIO(b"test")
    m.buffer(i)
    assert m.open().read() == b"test"

    with pytest.raises(ReceptorRuntimeError):
        i = io.StringIO("test")
        m.buffer(i)
