import asyncio
import collections
import logging
logger = logging.getLogger(__name__)

from .base import BaseBufferManager, BaseBuffer

class InMemoryBufferManager(BaseBufferManager):
    _buffers = {}

    def get_buffer_for_node(self, node_id):
        return self._buffers.setdefault(node_id, InMemoryBuffer(node_id))

class InMemoryBuffer(object):
    def __init__(self, node_id):
        super().__init__(node_id)
        self._buffer = collections.deque()
        self._lock = asyncio.Lock()

    def push(self, message):
        with (yield from self._lock):
            self._buffer.append(message)
    
    def pop(self):
        with (yield from self._lock):
            return self._buffer.popleft()
    
    def flush(self):
        with (yield from self._lock):
            to_return = list(self._buffer)
            self._buffer.clear()
        return to_return
