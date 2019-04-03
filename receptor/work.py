import importlib
import logging

from . import exceptions
from .messages import envelope
from . import router
logger = logging.getLogger(__name__)


class WorkManager:
    async def handle(self, inner_env):
        logger.info(f'Handling work for {inner_env.message_id} as {inner_env.directive}')
        namespace, action = inner_env.directive.split(':', 1)
        try:
            worker_module = importlib.import_module(f'receptor.worker.{namespace}')
        except ImportError:
            logger.exception(f'Error importing worker module for {namespace}')
            raise exceptions.UnknownDirective(f'Error loading directive handlers for {namespace}')
        try:
            action_method = getattr(worker_module, f'do_{action}')
        except AttributeError:
            logger.exception(f'Could not load action {action} from {namespace}')
            raise exceptions.InvalidDirectiveAction(f'Invalid action {action} for {namespace}')
        responses = action_method(inner_env)
        serial = 0
        async for response in responses:
            serial += 1
            logger.debug(f'Response emitted for {inner_env.message_id}, serial {serial}')
            enveloped_response = envelope.InnerEnvelope.make_response(
                recipient=inner_env.sender,
                payload=response,
                in_response_to=inner_env.message_id,
                serial=serial
            )
            await router.send(enveloped_response)


work_manager = WorkManager()
