import datetime
import json
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
        responses = action_method(router.receptor, inner_env)
        serial = 0
        async for response in responses:
            serial += 1
            enveloped_response = envelope.Inner.make_response(
                receptor=router.receptor,
                recipient=inner_env.sender,
                payload=response,
                in_response_to=inner_env.message_id,
                serial=serial
            )
            await router.send(enveloped_response)

    async def ping(self, receptor, inner_env):
        logger.info(f'Received ping from {inner_env.sender}')
        ping_packet = json.loads(inner_env.raw_payload)
        return_data = dict(initial_time=ping_packet['ts'],
                           response_time=datetime.datetime.utcnow().isoformat())
        if ping_packet['flags'] & 0b1:
            return_data['active_work'] = receptor.work_manager.get_work()
        if ping_packet['flags'] & 0b10:
            return_data['peering'] = receptor.get_connection_manifest()
        if ping_packet['flags'] & 0b100:
            return_data['capabilities'] = receptor.work_manager.get_capabilities()
        if ping_packet['flags'] & 0b1000:
            return_data['receptor'] = dict(version=receptor.receptor_version)

        yield json.dumps(return_data)


control = Control()
