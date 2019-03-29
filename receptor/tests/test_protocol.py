import pytest
from receptor import protocol


def test_databuffer():
    b = protocol.DataBuffer()
    msg = b"this is a test"
    s = protocol.DELIM + msg + protocol.DELIM
    b.add(s)
    m = next(b.get())
    assert m == msg


def test_databuffer_no_delim():
    b = protocol.DataBuffer()
    msg = b"this is a test"
    b.add(msg)
    with pytest.raises(StopIteration):
        next(b.get())
