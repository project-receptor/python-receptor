import logging
from .messages import envelope, directive
from . import router, work_manager

logger = logging.getLogger(__name__)

RECEPTOR_DIRECTIVE_NAMESPACE = 'receptor'
CONTROL_DIRECTIVES = ['ping']

async def handle_msg(msg):
    outer_env = envelope.OuterEnvelope.from_raw(msg)
    next_hop = await router.next_hop(outer_env.recipient)
    if next_hop is None:
        # it's a meee
        await outer_env.deserialize_inner()
        namespace, _ = outer_env.inner_obj.directive.split(':', 1)
        if namespace == 'receptor':
            await directive.control(outer_env.inner_obj)
        await work_manager.handle(outer_env.inner_obj)
    else:
        await router.forward(outer_env, next_hop)

