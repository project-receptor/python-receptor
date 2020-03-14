import asyncio
import queue


class BridgeQueue(queue.Queue):
    """
    BridgeQueue is a queue.Queue subclass intended to 'bridge' a real thread
    and a coroutine. Where the thread is the producer and the coroutine is
    the consumer.

    The queue implements the async iterator protocol for the consuming
    coroutine and exposes the normal queue.Queue for threads.

    Additionally, there is a sentinel value assigned to the queue that can be
    used to indicate when iteration should cease.
    """

    sentinel = object()

    def __aiter__(self):
        return self

    async def __anext__(self):
        sleep_time = 0.0
        while True:
            try:
                item = self.get_nowait()
                sleep_time = 0.0
                if item is self.sentinel:
                    raise StopAsyncIteration
                else:
                    return item
            except queue.Empty:
                await asyncio.sleep(sleep_time)
                sleep_time = min(1.0, sleep_time + 0.1)

    @classmethod
    def one(cls, item):
        """
        Constructs a BridgeQueue with the single provided item followed by
        the sentinel value.  This function does not block.
        """
        q = cls()
        q.put_nowait(item)
        q.close()
        return q

    def close(self):
        self.put_nowait(self.sentinel)

    def read_from(self, fp, chunk_size=2 ** 12):
        """
        Reads from a file-like object in chunk_size blocks and puts the bytes
        into the queue.

        Once the file has been read completely, the queue's sentinel value is
        placed into the queue, signaling to the consumer that all data has
        been read.
        """
        chunk = fp.read(chunk_size)
        while chunk:
            self.put(chunk)
            chunk = fp.read(chunk_size)
        self.put(self.sentinel)
