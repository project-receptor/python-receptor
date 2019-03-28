import logging
from .messages import envelope
from . import router, work_manager

logger = logging.getLogger(__name__)


async def handle_msg(msg):
    outer_env = envelope.OuterEnvelope.from_raw(msg)
    next_hop = await router.next_hop(outer_env.recipient)
    if next_hop is None:
        # it's a meee
        await outer_env.deserialize_inner()
        await work_manager.handle(outer_env.inner)
    else:
        await router.forward(outer_env, next_hop)
