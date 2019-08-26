import collections
import logging
import uuid
import json
import os

from .base import BaseBufferManager, BaseBuffer
from .exceptions import ReceptorBufferError

logger = logging.getLogger(__name__)


class FileBufferManager(BaseBufferManager):
    _buffers = {}

    def get_buffer_for_node(self, node_id, config):
        return self._buffers.setdefault(node_id, FileBuffer(node_id, config))


class FileBuffer(BaseBuffer):

    def __init__(self, node_id, config):
        super().__init__(node_id, config)
        self.node_id = node_id
        self.base_path = os.path.join(os.path.expanduser(self.config.server.data_dir))
        self.message_path = os.path.join(self.base_path, "messages")
        self.manifest_path = os.path.join(self.base_path, "manifest-{}".format(node_id))
        if not os.path.exists(self.message_path):
            os.makedirs(self.message_path, mode=0o700)


    def new_message(self):
        ident = str(uuid.uuid4())
        try:
            handle = open(os.path.join(self.message_path, ident), "wb")
        except Exception as e:
            raise ReceptorBufferError("Failed to generate new message file for {}: {}".format(self.node_id, e))
        return (ident, handle)

    def read_message(self, ident):
        try:
            message_data = open(os.path.join(self.message_path, ident), "rb").read()
            os.remove(os.path.join(self.message_path, ident))
        except Exception as e:
            raise ReceptorBufferError("Failed to handle message data file for {} {}: {}".format(self.node_id, ident, e))
        return message_data

    def write_manifest(self, manifest):
        try:
            fd = open(self.manifest_path, "w")
            json.dump(manifest, fd)
            fd.close()
        except Exception as e:
            raise ReceptorBufferError("Failed to handle metadata file for {}: {}".format(self.node_id, e))

    def read_manifest(self):
        if not os.path.exists(self.manifest_path):
            return []
        try:
            fd = open(self.manifest_path, "r")
            manifest = json.load(fd)
            return manifest
        except Exception as e:
            logger.warn("Failed to read manifest: {}".format(e))
            return []

    def push(self, message):
        manifest = self.read_manifest()
        ident, handle = self.new_message()
        try:
            handle.write(message)
            handle.close()
        except Exception as e:
            raise ReceptorBufferError("Failed to write message file for {} {}: {}".format(self.node_id, ident, e))
        manifest.append(ident)
        self.write_manifest(manifest)

    def pop(self):
        manifest = self.read_manifest()
        item = self.read_message(manifest.pop(0))
        self.write_manifest(manifest)
        return item
