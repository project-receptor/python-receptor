import collections
import logging

from .base import BaseBufferManager, BaseBuffer

logger = logging.getLogger(__name__)


class FileBufferManager(BaseBufferManager):
    _buffers = {}

    def get_buffer_for_node(self, node_id, config):
        return self._buffers.setdefault(node_id, FileBuffer(node_id, config))


class FileBuffer(BaseBuffer):

    def __init__(self, node_id, config):
        super().__init__(node_id, config)

    def get_file_handle(self, ident):
        return open(os.path.join(os.path.expanduser(self.config.server.data_dir),
                                 "messages",
                                 ident), "w")

    def update_manifest(self, ...): pass

    def push(self, message):
        
