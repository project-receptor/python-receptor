import logging
logger = logging.getLogger(__name__)


class BaseBufferManager:
    def get_buffer_for_node(self, node_id, receptor):
        raise NotImplementedError()


class BaseBuffer:
    node_id = None

    def __init__(self, node_id, receptor):
        self.node_id = node_id
        self.receptor = receptor

    def __iter__(self):
        raise NotImplementedError

    def __next__(self):
        raise NotImplementedError

    def push(self, message):
        raise NotImplementedError()

    def pop(self):
        raise NotImplementedError()

    def flush(self):
        raise NotImplementedError()
