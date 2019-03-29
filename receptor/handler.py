import logging
from .messages import envelope, directive
from . import router
from .work import work_manager
from . import exceptions

logger = logging.getLogger(__name__)

RECEPTOR_DIRECTIVE_NAMESPACE = 'receptor'


async def handle_msg(msg):
    outer_env = envelope.OuterEnvelope.from_raw(msg)
    next_hop = await router.next_hop(outer_env.recipient)
    if next_hop is None:
        await outer_env.deserialize_inner()
        if outer_env.inner_obj.message_type == 'directive':
            namespace, _ = outer_env.inner_obj.directive.split(':', 1)
            if namespace == 'receptor':
                await directive.control(outer_env.inner_obj)
            else:
                # other namespace/work directives
                await work_manager.handle(outer_env.inner_obj)
        elif outer_env.inner_obj.message_type == 'response':
            # Who the fuck knows?
            pass
        else:
            raise exceptions.UnknownMessageType(
                f'Unknown message type: {outer_env.inner_obj.message_type}')
    else:
        await router.forward(outer_env, next_hop)

