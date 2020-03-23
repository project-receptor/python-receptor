import sys
import asyncio
import os
import shutil
import tempfile

import pytest

from receptor.buffers.file import DurableBuffer
from receptor import fileio


@pytest.fixture
def tempdir():
    dir_ = tempfile.mkdtemp()
    yield dir_
    shutil.rmtree(dir_)


@pytest.mark.asyncio
async def test_with_open(event_loop, tempdir):
    with tempfile.NamedTemporaryFile() as fp:
        fp.write(b"hello")
        fp.flush()

        async with fileio.File(fp.name, "rb") as afp:
            data = await afp.read()
            assert data == b"hello"


@pytest.mark.asyncio
async def test_create(event_loop, tempdir):
    b = DurableBuffer(tempdir, "test_create", asyncio.get_event_loop())
    await b.put(b"some data")
    item = await b.get()
    async with fileio.File(item["path"]) as fp:
        data = await fp.read()
        assert data == b"some data"


@pytest.mark.asyncio
async def test_manifest(event_loop, tempdir):
    b = DurableBuffer(tempdir, "test_manifest", event_loop, write_time=0.0)
    await b.put(b"one")
    await b.put(b"two")
    await b.put(b"three")

    item = await b.get()
    async with fileio.File(item["path"]) as fp:
        data = await fp.read()
        assert data == b"one"


@pytest.mark.asyncio
async def test_chunks(event_loop, tempdir):
    b = DurableBuffer(tempdir, "test_chunks", event_loop, write_time=0.0)
    await b.put((b"one", b"two", b"three"))

    item = await b.get()
    async with fileio.File(item["path"]) as fp:
        data = await fp.read()
        assert data == b"onetwothree"


@pytest.mark.asyncio
async def test_unreadable_file(event_loop, tempdir):
    b = DurableBuffer(tempdir, "test_unreadable_file", event_loop)
    b.q._queue.appendleft("junk")
    await b.put(b"valid data")
    item = await b.get()
    async with fileio.File(item["path"]) as fp:
        data = await fp.read()
        assert data == b"valid data"
        assert b.q.empty()


@pytest.mark.asyncio
async def test_does_not_delete_messages(event_loop, tempdir):
    b = DurableBuffer(tempdir, "test_deletes_messages", event_loop, write_time=0.0)
    await b.put(b"some data")
    item = await b.get()
    async with fileio.File(item["path"]) as fp:
        data = await fp.read()
        assert data == b"some data"
        await b._manifest_clean.wait()
        assert os.path.exists(item["path"])
