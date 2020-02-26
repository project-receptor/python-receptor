import asyncio
import os
import shutil
import tempfile

import pytest

from receptor.buffers.file import DurableBuffer


@pytest.fixture
def tempdir():
    dir_ = tempfile.mkdtemp()
    yield dir_
    shutil.rmtree(dir_)


@pytest.mark.asyncio
async def test_create(event_loop, tempdir):
    b = DurableBuffer(tempdir, "test_create", event_loop)
    await b.put(b"some data")
    assert await b.get() == b"some data"


# this test is flaky because the manifest is written on a timer
# even with the timer set to 0.0, the order of operations can land
# in such a way that a very short (0.0) sleep isn't enough to ensure
# that the manifest will have all the items it should by the time we
# check
@pytest.mark.asyncio
async def test_manifest(event_loop, tempdir):
    b = DurableBuffer(tempdir, "test_manifest", event_loop, write_time=0.0)
    await b.put(b"one")
    await b.put(b"two")
    await b.put(b"three")
    assert b.q.qsize() == 3

    await asyncio.sleep(0.2)

    assert len(b._read_manifest()) == 3


@pytest.mark.asyncio
async def test_chunks(event_loop, tempdir):
    b = DurableBuffer(tempdir, "test_chunks", event_loop)
    await b.put((b"one", b"two", b"three"))
    assert b.q.qsize() == 1

    assert len(b._read_manifest()) == 1

    data = await b.get()
    assert data == b"onetwothree"

@pytest.mark.asyncio
@pytest.mark.skip(reason="Waiting on more durable buffer work")
async def test_unreadable_file(event_loop, tempdir):
    b = DurableBuffer(tempdir, "test_unreadable_file", event_loop)
    b.q._queue.appendleft("junk")
    await b.put(b"valid data")
    data = await b.get()
    assert data == b"valid data"
    assert b.q.empty()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Waiting on more durable buffer work")
async def test_deletes_messages(event_loop, tempdir):
    b = DurableBuffer(tempdir, "test_deletes_messages", event_loop)
    await b.put(b"some data")
    ident = b.q._queue[0]["ident"]
    assert await b.get() == b"some data"
    filepath = os.path.join(b._message_path, ident)
    assert not os.path.exists(filepath)
