import logging
logger = logging.getLogger(__name__)
from ..exceptions import UnknownDirective
from .. import router
from . import envelope

class Directive:
    def __init__(self, type_, payload):
        self.type_ = type_
        self.payload = payload

class Control:
    CONTROL_DIRECTIVES = ['ping']

    async def __call__(self, inner_env):
        _, action = inner_env.directive.split(':', 1)
        if not action in self.CONTROL_DIRECTIVES:
            raise UnknownDirective(f'Unknown control directive: {action}')
        action_method = getattr(self, action)
        responses = action_method(inner_env)
        serial = 0
        async for response in responses:
            serial += 1
            enveloped_response = envelope.InnerEnvelope.make_response(
                recipient=inner_env.sender,
                payload=response,
                in_response_to=inner_env.message_id,
                serial=serial
            )
            router.send(enveloped_response)

control = Control()