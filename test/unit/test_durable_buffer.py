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


@pytest.mark.asyncio
async def test_manifest(event_loop, tempdir):
    b = DurableBuffer(tempdir, "test_manifest", event_loop)
    await b.put(b"one")
    await b.put(b"two")
    await b.put(b"three")
    assert b.q.qsize() == 3

    assert await b.get() == b"one"
    assert await b.get() == b"two"
    assert await b.get() == b"three"


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
    ident = b.q._queue[0]
    assert await b.get() == b"some data"
    filepath = os.path.join(b._message_path, ident)
    assert not os.path.exists(filepath)
