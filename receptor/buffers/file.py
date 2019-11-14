import asyncio
import json
import logging
import os
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from ..exceptions import ReceptorBufferError
from .base import BaseBuffer, BaseBufferManager

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
        async with self._manifest_lock:
            ident = str(uuid.uuid4())
            await self._loop.run_in_executor(pool, self._write_file, data, ident)
            await self.q.put(ident)
            await self._save_manifest()
    
    async def get(self, handle_only=False):
        async with self._manifest_lock:
            msg = await self.q.get()
            await self._save_manifest()
            return await self._get_file(msg, handle_only=handle_only)
    
    async def _save_manifest(self):
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

    async def _get_file(self, path, handle_only=False):
        path = os.path.join(self._message_path, path)
        fp = await self._loop.run_in_executor(pool, open, path, "rb")
        if handle_only:
            return fp
        bytes = await self._loop.run_in_executor(pool, lambda: fp.read())
        fp.close()
        return bytes

    def _write_file(self, data, ident):
        with open(os.path.join(self._message_path, ident), "wb") as fp:
            fp.write(data)
        

class FileBufferManager(BaseBufferManager):
    _buffers = {}

    def get_buffer_for_node(self, node_id, receptor):
        return self._buffers.setdefault(node_id, FileBuffer(node_id, receptor))


class FileBuffer(BaseBuffer):

    def __init__(self, node_id, receptor):
        super().__init__(node_id, receptor)
        self.node_id = node_id
        self.loop = asyncio.get_event_loop()
        self.base_path = os.path.join(os.path.expanduser(self.receptor.config.default_data_dir))
        self.message_path = os.path.join(self.base_path, self.receptor.node_id, "messages")
        self.manifest_path = os.path.join(self.base_path, self.receptor.node_id, "manifest-{}".format(node_id))
        if not os.path.exists(self.message_path):
            os.makedirs(self.message_path, mode=0o700)

    def __iter__(self):
        self.current = 0
        return self

    def __next__(self):
        manifest = self.read_manifest()
        if len(manifest) <= self.current:
            raise StopIteration
        ident = manifest[self.current]
        current_payload = self.read(ident)
        self.current += 1
        return ident, current_payload

    def new_message(self):
        ident = str(uuid.uuid4())
        try:
            handle = open(os.path.join(self.message_path, ident), "wb")
        except Exception as e:
            raise ReceptorBufferError("Failed to generate new message file for {}: {}".format(self.node_id, e))
        return (ident, handle)

    def read_message(self, ident, remove=True):
        try:
            message_data = open(os.path.join(self.message_path, ident), "rb").read()
            if remove:
                os.remove(os.path.join(self.message_path, ident))
        except Exception as e:
            raise ReceptorBufferError("Failed to handle message data file for {} {}: {}".format(self.node_id, ident, e))
        return message_data

    def write_manifest(self, manifest):
        try:
            fd = open(self.manifest_path, "w")
            json.dump(manifest, fd)
            fd.close()
        except Exception as e:
            raise ReceptorBufferError("Failed to handle metadata file for {}: {}".format(self.node_id, e))

    def read_manifest(self):
        if not os.path.exists(self.manifest_path):
            return []
        try:
            fd = open(self.manifest_path, "r")
            manifest = json.load(fd)
            return manifest
        except Exception as e:
            logger.warn("Failed to read manifest: {}".format(e))
            return []

    def push(self, message):
        manifest = self.read_manifest()
        ident, handle = self.new_message()
        try:
            handle.write(message)
            handle.close()
        except Exception as e:
            raise ReceptorBufferError("Failed to write message file for {} {}: {}".format(self.node_id, ident, e))
        manifest.append(ident)
        self.write_manifest(manifest)

    def read(self, ident, remove=False):
        manifest = self.read_manifest()
        message = self.read_message(ident, remove=remove)
        if remove:
            manifest.remove(ident)
            self.write_manifest(manifest)
        return message

    def pop(self):
        manifest = self.read_manifest()
        item = self.read_message(manifest.pop(0))
        self.write_manifest(manifest)
        return item
