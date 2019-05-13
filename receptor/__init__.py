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
        notify_protocols = []
        for connection_node in self.connections:
            if protocol_obj in self.connections[connection_node]:
                logger.info("Removing connection {} for node {}".format(protocol_obj, connection_node))
                self.connections[connection_node].remove(protocol_obj)
                self.router.update_node(self.node_id, connection_node, 100)
                self.router.debug_router()
            notify_protocols += self.connections[connection_node]
        # TODO: Broadcast update, set timer for full expiration
        for active_protocol in notify_protocols:
            active_protocol.send_route_advertisement(self.router.get_edges())

    async def shutdown_handler(self):
        while True:
            if self.stop:
                return
            await asyncio.sleep(1)
