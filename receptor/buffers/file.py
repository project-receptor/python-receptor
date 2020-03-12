import asyncio
import datetime
import logging
import os
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from json.decoder import JSONDecodeError

from .. import serde as json

logger = logging.getLogger(__name__)
pool = ThreadPoolExecutor()


class DurableBuffer:

    def __init__(self, dir_, key, loop, write_time=1.0):
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
        self._loop.create_task(self.manifest_writer(write_time))

    async def put(self, framed_message):
        item = {
            "ident": str(uuid.uuid4()),
            "expire_time": datetime.datetime.utcnow() + datetime.timedelta(minutes=5),
        }
        await self._loop.run_in_executor(pool, self._write_file, framed_message, item)
        await self.q.put(item)
        self._manifest_dirty = True

    async def put_ident(self, ident):
        await self.q.put(ident)
        self._manifest_dirty = True

    async def get(self, handle_only=False, delete=True):
        while True:
            ident = await self.q.get()
            self._manifest_dirty = True
            try:
                f = await self._get_file(ident["ident"], handle_only=handle_only, delete=delete)
                return (ident, f)
            except (FileNotFoundError, TypeError):
                pass

    def _write_manifest(self):
        with open(self._manifest_path, "w") as fp:
            fp.write(json.dumps(list(self.q._queue)))

    def _read_manifest(self):
        try:
            with open(self._manifest_path, "r") as fp:
                return json.load(fp)
        except FileNotFoundError:
            return []
        except JSONDecodeError:
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
            if isinstance(data, bytes):
                fp.write(data)
            else:
                for chunk in data:
                    fp.write(chunk)

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


class FileBufferManager(defaultdict):

    def __init__(self, path, loop=asyncio.get_event_loop()):
        self.path = path
        self.loop = loop

    def __missing__(self, key):
        self[key] = DurableBuffer(self.path, key, self.loop)
        return self[key]
