import os
import uuid
import asyncio
import logging

from .config import ReceptorConfig
from .router import MeshRouter
from .work import WorkManager

logger = logging.getLogger(__name__)

class Receptor:
    def __init__(self, config=None, node_id=None, router_cls=None, 
                 work_manager_cls=None):
        self.config = config or ReceptorConfig()
        self.node_id = node_id or config.receptor.node_id or self._find_node_id()
        self.router = (router_cls or MeshRouter)(self)
        self.work_manager = (work_manager_cls or WorkManager)(self)
        self.connections = dict()
        self.stop = False

    def _find_node_id(self):
        if 'RECEPTOR_NODE_ID' in os.environ:
            return os.environ['RECEPTOR_NODE_ID']
        
        node_id = uuid.uuid4()
        if os.path.exists(os.path.join(os.getcwd(), 'Pipfile')):
            with open(os.path.join(os.getcwd(), '.env'), 'w+') as ofs:
                ofs.write(f'\nRECEPTOR_NODE_ID={node_id}\n')

    def add_connection(self, id_, protocol_obj):
        if id_ in self.connections:
            self.connections[id_].append(protocol_obj)
        else:
            self.connections[id_] = [protocol_obj]

    def remove_connection(self, protocol_obj):
        for node_id in self.connections:
            if protocol_obj in self.connections[node_id]:
                logger.info("Removing connection {} for node {}".format(protocol_obj, node_id))
                self.connections[node_id].remove(protocol_obj)

    async def shutdown_handler(self):
        while True:
            if self.stop:
                return
            await asyncio.sleep(1)
