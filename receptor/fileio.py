import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

pool = ThreadPoolExecutor()
loop = asyncio.get_event_loop()
run_in_executor = partial(loop.run_in_executor, pool)


class Opened:
    def __init__(self, path, mode):
        self.path = path
        self.mode = mode
        self._fp = None

    async def __aenter__(self):
        self._fp = await run_in_executor(open, self.path, self.mode)
        return self._fp

    async def __aexit__(self, exc_type, exc, tb):
        self._fp.close()
