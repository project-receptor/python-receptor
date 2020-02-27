import datetime
import logging

from ..exceptions import UnknownDirective
from .framed import FileBackedBuffer, FramedMessage

logger = logging.getLogger(__name__)


class Directive:
    def __init__(self, type_, payload):
        self.type_ = type_
        self.payload = payload


class Control:
    CONTROL_DIRECTIVES = ['ping']

    async def __call__(self, router, msg):
        _, action = msg.header["directive"].split(':', 1)
        if action not in self.CONTROL_DIRECTIVES:
            raise UnknownDirective(f'Unknown control directive: {action}')
        action_method = getattr(self, action)
        serial = 0
        async for response in action_method(router.receptor, msg):
            serial += 1
            resp_msg = FramedMessage(header=dict(
                recipient=msg.header["sender"],
                in_response_to=msg.msg_id,
                serial=serial
            ), payload=FileBackedBuffer.from_dict(response))
            await router.send(resp_msg)

    async def ping(self, receptor, msg):
        logger.info(f'Received ping from {msg.header["sender"]}')
        yield dict(
            initial_time=msg.header["timestamp"],
            response_time=str(datetime.datetime.utcnow()),
            active_work=receptor.work_manager.get_work())


control = Control()
