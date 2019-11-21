import json
import uuid

import pytest

from receptor.messages.envelope import Frame, FramedBuffer, gen_chunks


@pytest.yield_fixture
def msg_id():
    return uuid.uuid4().int


@pytest.yield_fixture
def framed_buffer():
    return FramedBuffer()


@pytest.mark.asyncio
async def test_framedbuffer(framed_buffer, msg_id):
    header = {"sender": "node1", "recipient": "node2", "route_list": []}
    header_bytes = json.dumps(header).encode("utf-8")
    f1 = Frame(Frame.Types.HEADER, 1, len(header_bytes), msg_id, 1)

    await framed_buffer.put(f1.serialize() + header_bytes)

    payload = b"tina loves butts"
    payload2 = b"yep yep yep"
    f2 = Frame(Frame.Types.PAYLOAD, 1, len(payload) + len(payload2), msg_id, 2)

    await framed_buffer.put(f2.serialize() + payload)
    await framed_buffer.put(payload2)

    m = await framed_buffer.get()

    assert m.header == header
    assert m.payload == payload + payload2


@pytest.mark.asyncio
async def test_gen_chunks():

    b = FramedBuffer()

    header = {"sender": "node1", "recipient": "node2", "route_list": []}
    payload = b"this is a test with a buffer"
    for chunk in gen_chunks(payload, header):
        await b.put(chunk)

    m = await b.get()
    assert m.header == header
    assert m.payload == payload


@pytest.mark.asyncio
async def test_hi(msg_id, framed_buffer):
    hi = json.dumps({"cmd": "hi"}).encode("utf-8")
    f1 = Frame(Frame.Types.PAYLOAD, 1, len(hi), msg_id, 1)

    await framed_buffer.put(f1.serialize())
    await framed_buffer.put(hi)

    m = await framed_buffer.get()

    assert m.header is None
    assert m.payload == hi


@pytest.mark.asyncio
async def test_extra_header(framed_buffer, msg_id):
    h1 = {"sender": "node1", "recipient": "node2", "route_list": []}
    payload = json.dumps(h1).encode("utf-8")
    f1 = Frame(Frame.Types.HEADER, 1, len(payload), msg_id, 1)
    await framed_buffer.put(f1.serialize())
    await framed_buffer.put(payload)

    h2 = {"sender": "node3", "recipient": "node4", "route_list": []}
    payload = json.dumps(h2).encode("utf-8")
    f2 = Frame(Frame.Types.HEADER, 1, len(payload), msg_id, 2)
    await framed_buffer.put(f2.serialize())
    await framed_buffer.put(payload)

    assert framed_buffer.header == h2


@pytest.mark.asyncio
async def test_command(framed_buffer, msg_id):
    cmd = {"cmd": "hi"}
    payload = json.dumps(cmd).encode("utf-8")
    f1 = Frame(Frame.Types.COMMAND, 1, len(payload), msg_id, 1)
    await framed_buffer.put(f1.serialize())
    await framed_buffer.put(payload)

    m = await framed_buffer.get()
    assert m.header == cmd
    assert m.payload is None
