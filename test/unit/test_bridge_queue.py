import pytest

from receptor.connection.base import BridgeQueue


async def read_all(q):
    buf = []
    async for item in q:
        buf.append(item)
    return buf


@pytest.mark.asyncio
async def test_one(event_loop):
    bq = BridgeQueue.one(b"this is a test")
    buf = await read_all(bq)
    assert buf[0] == b"this is a test"
