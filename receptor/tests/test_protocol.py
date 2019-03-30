import pytest
from receptor import protocol


def test_databuffer():
    b = protocol.DataBuffer()
    msg = b"this is a test"
    s = protocol.DELIM + msg + protocol.DELIM
    b.add(s)
    it = b.get()
    assert next(it) == b""
    assert next(it) == msg


def test_databuffer_no_delim():
    b = protocol.DataBuffer()
    msg = b"this is a test"
    b.add(msg)
    with pytest.raises(StopIteration):
        next(b.get())


def test_databuffer_many_msgs():
    b = protocol.DataBuffer()
    msg = [b"first bit", b"second bit", b"third bit unfinished"]
    b.add(protocol.DELIM.join(msg))
    it = b.get()
    assert next(it) == msg[0]
    assert next(it) == msg[1]
    with pytest.raises(StopIteration):
        next(it)
