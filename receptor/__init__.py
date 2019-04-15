import os
import uuid
import asyncio

from .config import ReceptorConfig
from .router import MeshRouter
from .work import WorkManager


class Receptor:
    def __init__(self, config=None, node_id=None, router_cls=None, 
                 work_manager_cls=None):
        self.config = config or ReceptorConfig()
        self.node_id = node_id or config.receptor.node_id or self._find_node_id()
        self.router = (router_cls or MeshRouter)(self)
        self.work_manager = (work_manager_cls or WorkManager)(self)
        self.stop = False

    def _find_node_id(self):
        if 'RECEPTOR_NODE_ID' in os.environ:
            return os.environ['RECEPTOR_NODE_ID']
        
        node_id = uuid.uuid4()
        if os.path.exists(os.path.join(os.getcwd(), 'Pipfile')):
            with open(os.path.join(os.getcwd(), '.env'), 'w+') as ofs:
                ofs.write(f'\nRECEPTOR_NODE_ID={node_id}\n')

    async def shutdown_handler(self):
        while True:
            if self.stop:
                return
            await asyncio.sleep(1)
