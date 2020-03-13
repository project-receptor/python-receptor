import asyncio
import datetime
import json
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import dateutil.parser

from .base import BaseBufferManager

logger = logging.getLogger(__name__)
pool = ThreadPoolExecutor()


def encode_date(obj):
    if isinstance(obj, datetime.datetime):
        return {
            "_type": "datetime.datetime",
            "value": obj.isoformat(),
        }
    raise TypeError


def decode_date(o):
    type_ = o.get("_type")
    if type_ != "datetime.datetime":
        return o
    return dateutil.parser.parse(o["value"])


class DurableBuffer:

    def __init__(self, dir_, key, loop):
        self.q = asyncio.Queue()
        self._base_path = os.path.join(os.path.expanduser(dir_))
        self._message_path = os.path.join(self._base_path, "messages")
        self._manifest_path = os.path.join(self._base_path, f"manifest-{key}")
        self._loop = loop
        self._manifest_lock = asyncio.Lock(loop=self._loop)
        self._manifest_dirty = False
        try:
            os.makedirs(self._message_path, mode=0o700)
        except Exception:
            pass
        for item in self._read_manifest():
            self.q.put_nowait(item)

        self._loop.create_task(self.manifest_writer(1.0))

    async def put(self, data):
        item = {
            "ident": str(uuid.uuid4()),
            "expire_time": datetime.datetime.utcnow() + datetime.timedelta(minutes=5),
        }
        await self._loop.run_in_executor(pool, self._write_file, data, item)
        await self.q.put(item)
        self._manifest_dirty = True

    async def get(self, handle_only=False, delete=True):
        while True:
            msg = await self.q.get()
            self._manifest_dirty = True
            try:
                return await self._get_file(msg["ident"], handle_only=handle_only, delete=delete)
            except FileNotFoundError:
                pass

    async def _save_manifest(self):
        async with self._manifest_lock:
            await self._loop.run_in_executor(pool, self._write_manifest)

    def _write_manifest(self):
        with open(self._manifest_path, "w") as fp:
            fp.write(json.dumps(list(self.q._queue), default=encode_date))

    def _read_manifest(self):
        try:
            with open(self._manifest_path, "r") as fp:
                return json.load(fp, object_hook=decode_date)
        except FileNotFoundError:
            return []
        except json.decoder.JSONDecodeError:
            with open(self._manifest_path, "r") as fp:
                logger.error("failed to decode manifest: %s", fp.read())
            raise

    def _path_for_ident(self, ident):
        return os.path.join(self._message_path, ident)

    def _remove_path(self, path):
        if os.path.exists(path):
            os.remove(path)
        else:
            logger.info("Can't remove {}, doesn't exist".format(path))

    async def _get_file(self, ident, handle_only=False, delete=True):
        """
        Retrieves a file from disk. If handle_only is True then we will
        return the handle to the file and do nothing else. Otherwise the file
        is read into memory all at once and returned. If delete is True (the
        default) and handle_only is False (the default) then the underlying
        file will be removed as well.
        """
        path = self._path_for_ident(ident)
        fp = await self._loop.run_in_executor(pool, open, path, "rb")
        if handle_only:
            return fp
        bytes_ = await self._loop.run_in_executor(pool, fp.read)
        fp.close()
        if delete:
            await self._loop.run_in_executor(pool, os.remove, path)
        return bytes_

    def _write_file(self, data, item):
        with open(os.path.join(self._message_path, item["ident"]), "wb") as fp:
            fp.write(data)

    async def expire(self):
        async with self._manifest_lock:
            new_queue = asyncio.Queue()
            while self.q.qsize() > 0:
                item = await self.q.get()
                ident = item["ident"]
                expire_time = item["expire_time"]
                if expire_time < datetime.datetime.utcnow():
                    logger.info("Expiring message %s", ident)
                    # TODO: Do something with expired message
                    await self._loop.run_in_executor(pool, self._remove_path, self._path_for_ident(ident))
                else:
                    await new_queue.put(item)
            self.q = new_queue
            self._write_manifest()

    async def manifest_writer(self, write_time):
        while True:
            if self._manifest_dirty:
                async with self._manifest_lock:
                    await self._loop.run_in_executor(pool, self._write_manifest)
                    self._manifest_dirty = False
            await asyncio.sleep(write_time)


class FileBufferManager(BaseBufferManager):
    _buffers = {}

    def get_buffer_for_node(self, node_id, receptor):
        # due to the way that the manager is constructed, we won't have enough
        # information to build a proper defaultdict at the time, and we want to
        # make sure we only construct a single instance of DurableBuffer
        # per-node so.. doing this the hard way.
        if node_id not in self._buffers:
            path = os.path.join(os.path.expanduser(receptor.base_path))
            self._buffers[node_id] = DurableBuffer(path, node_id, asyncio.get_event_loop())
        return self._buffers[node_id]
