import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

pool = ThreadPoolExecutor()


class Deferrer:
    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()

    async def defer(self, func, *args):
        """defers execution of the callable to the loop"""
        return await self.loop.run_in_executor(pool, func, *args)


class File:
    def __init__(self, name=None, mode="rb", deferrer=None):
        self.name = name
        self.mode = mode
        self.fileobj = None
        self.deferrer = deferrer or Deferrer()

    async def __aenter__(self):
        if not self.fileobj:
            self.fileobj = await self.deferrer.defer(open, self.name, self.mode)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.close()

    async def read(self, size=-1):
        return await self.deferrer.defer(self.fileobj.read, size)

    async def write(self, data):
        return await self.deferrer.defer(self.fileobj.write, data)

    def close(self):
        self.fileobj.close()
