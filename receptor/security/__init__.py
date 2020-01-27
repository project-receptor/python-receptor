import json
import logging

logger = logging.getLogger(__name__)


class MallCop:

    async def verify_node(self, node):
        return True

    async def verify_controller(self, controller):
        return True

    async def verify_msg(self, msg):
        return msg

    async def verify_directive(self, directive):
        return True

    async def verify_response(self, response):
        return True

    async def sign_response(self, inner_envelope):
        def strattr(attr):
            attrval = getattr(inner_envelope, attr)
            if type(attrval) == bytes:
                return attrval.decode()
            return attrval
        return json.dumps(
            {attr: strattr(attr)
             for attr in ['message_id', 'sender', 'recipient', 'message_type',
                          'timestamp', 'raw_payload', 'directive',
                          'in_response_to', 'ttl', 'serial', 'code']}
        ).encode("utf-8")
