import json
import uuid

import pytest

from receptor.messages.envelope import Frame, FramedBuffer, Header, gen_chunks


@pytest.yield_fixture
def msg_id():
    return uuid.uuid4().int


@pytest.yield_fixture
def framed_buffer():
    return FramedBuffer()


@pytest.mark.asyncio
async def test_framedbuffer(framed_buffer, msg_id):
    header = Header("node1", "node2", [])
    header_bytes = header.serialize()
    f1 = Frame(Frame.HEADER, 1, len(header_bytes), msg_id, 1)

    await framed_buffer.put(f1.serialize() + header_bytes)

    payload = b"tina loves butts"
    payload2 = b"yep yep yep"
    f2 = Frame(Frame.PAYLOAD, 1, len(payload) + len(payload2), msg_id, 2)

    await framed_buffer.put(f2.serialize() + payload)
    await framed_buffer.put(payload2)

    h, p = await framed_buffer.get()

    assert h == header
    assert p == payload + payload2


@pytest.mark.asyncio
async def test_gen_chunks():

    b = FramedBuffer()

    header = Header("node1", "node2", [])
    payload = b"this is a test with a buffer"
    for chunk in gen_chunks(payload, header):
        await b.put(chunk)

    h, p = await b.get()
    assert h == header
    assert p == payload


@pytest.mark.asyncio
async def test_hi(msg_id, framed_buffer):
    hi = json.dumps({"cmd": "hi"}).encode("utf-8")
    f1 = Frame(Frame.PAYLOAD, 1, len(hi), msg_id, 1)

    await framed_buffer.put(f1.serialize())
    await framed_buffer.put(hi)

    h, p = await framed_buffer.get()

    assert h is None
    assert p == hi


@pytest.mark.asyncio
async def test_extra_header(framed_buffer, msg_id):
    h1 = Header("node1", "node2", [])
    payload = h1.serialize()
    f1 = Frame(Frame.HEADER, 1, len(payload), msg_id, 1)
    await framed_buffer.put(f1.serialize())
    await framed_buffer.put(payload)

    h2 = Header("node3", "node4", [])
    payload = h2.serialize()
    f2 = Frame(Frame.HEADER, 1, len(payload), msg_id, 2)
    await framed_buffer.put(f2.serialize())
    await framed_buffer.put(payload)

    assert framed_buffer.header == h2
