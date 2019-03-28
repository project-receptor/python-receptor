import logging
logger = logging.getLogger(__name__)


class MallCop:

    async def verify_node(self, node):
        return True

    async def verify_controller(self, controller):
        return True

    async def verify_msg(self, msg):
        return True

    async def verify_directive(self, directive):
        return True

    async def verify_response(self, response):
        return True
