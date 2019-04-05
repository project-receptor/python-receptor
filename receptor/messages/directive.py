import datetime
import logging

from ..exceptions import UnknownDirective
from . import envelope

logger = logging.getLogger(__name__)


class Directive:
    def __init__(self, type_, payload):
        self.type_ = type_
        self.payload = payload


class Control:
    CONTROL_DIRECTIVES = ['ping']

    async def __call__(self, router, inner_env):
        _, action = inner_env.directive.split(':', 1)
        if action not in self.CONTROL_DIRECTIVES:
            raise UnknownDirective(f'Unknown control directive: {action}')
        action_method = getattr(self, action)
        responses = action_method(inner_env)
        serial = 0
        async for response in responses:
            serial += 1
            enveloped_response = envelope.InnerEnvelope.make_response(
                receptor=router.receptor,
                recipient=inner_env.sender,
                payload=response,
                in_response_to=inner_env.message_id,
                serial=serial
            )
            await router.send(enveloped_response)
    
    async def ping(self, inner_env):
        logger.info(f'Received ping from {inner_env.sender}')
        yield f'{inner_env.raw_payload}|{datetime.datetime.utcnow().isoformat()}'


control = Control()
