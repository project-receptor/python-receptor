import asyncio
import json
import logging
import os
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from .base import BaseBufferManager

logger = logging.getLogger(__name__)
pool = ThreadPoolExecutor()


class DurableBuffer:

    def __init__(self, dir_, key, loop):
        self.q = asyncio.Queue()
        self._base_path = os.path.join(os.path.expanduser(dir_))
        self._message_path = os.path.join(self._base_path, "messages")
        self._manifest_path = os.path.join(self._base_path, f"manifest-{key}")
        self._loop = loop
        self._manifest_lock = asyncio.Lock(loop=self._loop)
        try:
            os.makedirs(self._message_path, mode=0o700)
        except Exception:
            pass
        # We are setting the internal queue for the asyncio Queue to have a
        # default from what we have in the manifest. This relies on an
        # implementation detail of asyncio.Queue because there doesn't appear
        # to be a way to set initial state otherwise
        self.q._queue = deque(self._read_manifest())
    
    async def put(self, data):
        ident = str(uuid.uuid4())
        await self._loop.run_in_executor(pool, self._write_file, data, ident)
        await self.q.put(ident)
        await self._save_manifest()
    
    async def get(self, handle_only=False, delete=True):
        while True:
            msg = await self.q.get()
            await self._save_manifest()
            try:
                return await self._get_file(msg, handle_only=handle_only, delete=delete)
            except FileNotFoundError:
                pass
    
    async def _save_manifest(self):
        async with self._manifest_lock:
            await self._loop.run_in_executor(pool, self._write_manifest)
    
    def _write_manifest(self):
        with open(self._manifest_path, "w") as fp:
            json.dump(list(self.q._queue), fp)
    
    def _read_manifest(self):
        try:
            with open(self._manifest_path, "r") as fp:
                return json.load(fp)
        except FileNotFoundError:
            return []

    def _path_for_ident(self, ident):
        return os.path.join(self._message_path, ident)

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
        bytes = await self._loop.run_in_executor(pool, lambda: fp.read())
        fp.close()
        if delete:
            await self._loop.run_in_executor(pool, os.remove, path)
        return bytes

    def _write_file(self, data, ident):
        with open(os.path.join(self._message_path, ident), "wb") as fp:
            fp.write(data)

    async def expire(self):
        async with self._manifest_lock:
            new_queue = asyncio.Queue()
            while self.q.qsize() > 0:
                ident = await self.q.get()
                data = await self._get_file(ident, handle_only=True, delete=False)
                msg = json.load(data)
                if "expire_time" in msg and msg['expire_time'] < time.time():
                    logger.info("Expiring message %s", ident)
                    # TODO: Do something with expired message
                    await self._loop.run_in_executor(pool, os.remove, self._path_for_ident(ident))
                else:
                    await new_queue.put(ident)
            self.q = new_queue



        

class FileBufferManager(BaseBufferManager):
    _buffers = {}

    def get_buffer_for_node(self, node_id, receptor):
        path = os.path.join(os.path.expanduser(receptor.config.default_data_dir))
        return self._buffers.setdefault(node_id, DurableBuffer(path, node_id, asyncio.get_event_loop()))
