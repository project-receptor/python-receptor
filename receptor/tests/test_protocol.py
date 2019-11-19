import io
import uuid

import pytest

from receptor import protocol
from receptor.messages.envelope import Frame, FramedBuffer, Header, gen_chunks


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


@pytest.mark.asyncio
async def test_framedbuffer():
    b = FramedBuffer()

    msg_id = uuid.uuid4().int
    header = Header("node1", "node2", [])
    header_bytes = header.serialize()
    f1 = Frame(Frame.START_MSG, 1, len(header_bytes), msg_id, 1)

    await b.put(f1.serialize() + header_bytes)

    payload = b"tina loves butts"
    payload2 = b"yep yep yep"
    f2 = Frame(Frame.PAYLOAD, 1, len(payload) + len(payload2), msg_id, 2)

    await b.put(f2.serialize() + payload)    
    await b.put(payload2)

    h, p = await b.get()

    assert h == header
    assert p == payload + payload2


@pytest.mark.asyncio
async def test_gen_chunks():

    b = FramedBuffer()

    header = Header("node1", "node2", [])
    payload = b"this is a test with a buffer"
    for chunk in gen_chunks(io.BytesIO(payload), header):
        await b.put(chunk)
    
    h, p = await b.get()
    assert h == header
    assert p == payload
