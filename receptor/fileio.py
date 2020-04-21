import atexit
import asyncio
from concurrent.futures import ThreadPoolExecutor

pool = ThreadPoolExecutor()


def shutdown_pool():
    for thread in pool._threads:
        thread._tstate_lock.release()


atexit.register(shutdown_pool)


class Deferrer:
    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()

    async def defer(self, func, *args):
        """defers execution of the callable to the loop"""
        return await self.loop.run_in_executor(pool, func, *args)


async def read(path, mode="rb"):
    def _f():
        with open(path, mode) as fp:
            return fp.read()

    return await Deferrer().defer(_f)


async def writelines(path, data, mode="wb"):
    def _f():
        with open(path, mode) as fp:
            fp.writelines(data)

    return await Deferrer().defer(_f)


async def write(path, data, mode="wb"):
    def _f():
        with open(path, mode) as fp:
            fp.write(data)

    return await Deferrer().defer(_f)
