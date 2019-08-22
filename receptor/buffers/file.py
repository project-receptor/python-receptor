import collections
import logging
import uuid
import json
import os

from .base import BaseBufferManager, BaseBuffer

logger = logging.getLogger(__name__)


class FileBufferManager(BaseBufferManager):
    _buffers = {}

    def get_buffer_for_node(self, node_id, config):
        return self._buffers.setdefault(node_id, FileBuffer(node_id, config))


class FileBuffer(BaseBuffer):

    def __init__(self, node_id, config):
        super().__init__(node_id, config)
        self.base_path = os.path.join(os.path.expanduser(self.config.server.data_dir))
        self.message_path = os.path.join(self.base_path, "messages")
        self.manifest_path = os.path.join(self.base_path, "manifest-{}".format(node_id))
        if not os.path.exists(self.message_path):
            os.makedirs(self.message_path, mode=0o700)


    def new_message(self):
        ident = str(uuid.uuid4())
        return (ident, open(os.path.join(self.message_path, ident), "wb"))

    def read_message(self, ident):
        # TODO: Error handling
        message_data = open(os.path.join(self.message_path, ident), "rb").read()
        os.remove(os.path.join(self.message_path, ident))
        return message_data

    def remove_message(self, ident):
        os.remove(os.path.join(self.message_path, ident))

    def write_manifest(self, manifest):
        fd = open(self.manifest_path, "w")
        json.dump(manifest, fd)
        fd.close()

    def read_manifest(self):
        if not os.path.exists(self.manifest_path):
            return []
        try:
            fd = open(self.manifest_path, "r")
            manifest = json.load(fd)
            return manifest
        except Exception as e: # TODO: More specific
            logger.error("Failed to read manifest: {}".format(e))
            return []

    def push(self, message):
        manifest = self.read_manifest()
        ident, handle = self.new_message()
        handle.write(message)
        handle.close()
        manifest.append(ident)
        self.write_manifest(manifest)

    def pop(self):
        manifest = self.read_manifest()
        item = self.read_message(manifest.pop(0))
        self.write_manifest(manifest)
        return item
