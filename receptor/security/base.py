import logging

logger = logging.getLogger(__name__)


class BaseSecurityManager:
    def __init__(self, receptor):
        self.receptor = receptor

    async def verify_node(self, node):
        raise NotImplementedError('Override in subclass.')

    async def verify_controller(self, controller):
        raise NotImplementedError('Override in subclass.')

    async def verify_msg(self, msg):
        raise NotImplementedError('Override in subclass.')

    async def verify_directive(self, directive):
        raise NotImplementedError('Override in subclass.')

    async def verify_response(self, response):
        raise NotImplementedError('Override in subclass.')
    
    async def sign_response(self, inner_envelope):
        raise NotImplementedError('Override in subclass.')