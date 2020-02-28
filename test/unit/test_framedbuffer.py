import asyncio
import json
import uuid

import pytest

from receptor.messages.envelope import Frame, FramedBuffer, FramedMessage


@pytest.fixture
def msg_id():
    return uuid.uuid4().int


@pytest.fixture
def framed_buffer(event_loop):
    return FramedBuffer(loop=event_loop)


@pytest.mark.asyncio
async def test_framedbuffer(framed_buffer, msg_id):
    header = {"sender": "node1", "recipient": "node2", "route_list": []}
    header_bytes = json.dumps(header).encode("utf-8")
    f1 = Frame(Frame.Types.HEADER, 1, len(header_bytes), msg_id, 1)

    await framed_buffer.put(f1.serialize() + header_bytes)

    payload = b"payload one is very boring"
    payload2 = b"payload two is also very boring"
    f2 = Frame(Frame.Types.PAYLOAD, 1, len(payload) + len(payload2), msg_id, 2)

    await framed_buffer.put(f2.serialize() + payload)
    await framed_buffer.put(payload2)

    m = await framed_buffer.get()

    assert m.header == header
    assert m.payload == payload + payload2


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


@pytest.mark.asyncio
async def test_overfull(framed_buffer, msg_id):
    header = {"foo": "bar"}
    payload = b"this is a test"
    msg = FramedMessage(header=header, payload=payload)

    await framed_buffer.put(msg.serialize())

    m = await framed_buffer.get()

    assert m.header == header
    assert m.payload == payload


@pytest.mark.asyncio
async def test_underfull(framed_buffer, msg_id):
    header = {"foo": "bar"}
    payload = b"this is a test"
    msg = FramedMessage(header=header, payload=payload)
    b = msg.serialize()

    await framed_buffer.put(b[:10])
    await framed_buffer.put(b[10:])

    m = await framed_buffer.get()

    assert m.header == header
    assert m.payload == payload


@pytest.mark.asyncio
async def test_malformed_frame(framed_buffer, msg_id):
    with pytest.raises(ValueError):
        await framed_buffer.put(
            b"this is total garbage and should break things very nicely"
        )


@pytest.mark.asyncio
async def test_too_short(framed_buffer, msg_id):
    f1 = Frame(Frame.Types.HEADER, 1, 100, 1, 1)
    too_short_header = b"this is not long enough"
    f2 = Frame(Frame.Types.PAYLOAD, 1, 100, 1, 2)
    too_short_payload = b"this is also not long enough"

    await framed_buffer.put(f1.serialize() + too_short_header)
    await framed_buffer.put(f2.serialize() + too_short_payload)

    with pytest.raises(asyncio.QueueEmpty):
        framed_buffer.get_nowait()
