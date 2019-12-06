from . import Transport


class RawSocket(Transport):
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self._closed = False

    async def __anext__(self):
        return await self.reader.read()

    @property
    def closed(self):
        return self._closed

    async def close(self):
        self._closed = True
        await self.writer.close()

    async def send(self, bytes_):
        self.writer.write(bytes_)
        await self.writer.drain()
