import pytest

from receptor import protocol


def deser(x):
    return x


@pytest.mark.asyncio
async def test_databuffer():
    b = protocol.DataBuffer(deserializer=deser)
    msg = b"this is a test"
    s = protocol.DELIM + msg + protocol.DELIM
    b.add(s)
    assert await b.get() == b""
    assert await b.get() == msg


def test_databuffer_no_delim():
    b = protocol.DataBuffer(deserializer=deser)
    msg = b"this is a test"
    b.add(msg)
    assert b.q.empty()


@pytest.mark.asyncio
async def test_databuffer_many_msgs():
    b = protocol.DataBuffer(deserializer=deser)
    msg = [b"first bit", b"second bit", b"third bit unfinished"]
    b.add(protocol.DELIM.join(msg))
    assert msg[0] == await b.get()
    assert msg[1] == await b.get()
    assert b.q.empty()
