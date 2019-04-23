import collections
import logging

from .base import BaseBufferManager, BaseBuffer

logger = logging.getLogger(__name__)


class InMemoryBufferManager(BaseBufferManager):
    _buffers = {}

    def get_buffer_for_node(self, node_id):
        return self._buffers.setdefault(node_id, InMemoryBuffer(node_id))


# NOTE: This is not thread safe
class InMemoryBuffer(BaseBuffer):
    def __init__(self, node_id):
        super().__init__(node_id)
        self._buffer = collections.deque()

    def push(self, message):
        logger.debug(f'Pushing a message to {self.node_id} buffer.')
        self._buffer.append(message)
    
    def pop(self):
        return self._buffer.popleft()
    
    def flush(self):
        logger.debug(f'Flushing buffer for {self.node_id}')
        to_return = list(self._buffer)
        self._buffer.clear()
        return to_return
