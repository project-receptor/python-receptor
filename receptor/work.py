import pkg_resources
import logging

from . import exceptions
from .messages import envelope
logger = logging.getLogger(__name__)


class WorkManager:
    def __init__(self, receptor):
        self.receptor = receptor

    def load_receptor_worker(self, name):
        entry_points = [x for x in filter(lambda x: x.name == name,
                                          pkg_resources.iter_entry_points("receptor.worker"))]
        if not entry_points:
            raise exceptions.UnknownDirective(f"Error loading directive handlers for {name}")
        return entry_points[0].load()

    async def handle(self, inner_env):
        logger.info(f'Handling work for {inner_env.message_id} as {inner_env.directive}')
        namespace, action = inner_env.directive.split(':', 1)
        worker_module = self.load_receptor_worker(namespace)
        try:
            action_method = getattr(worker_module, f'{action}')
        except AttributeError:
            logger.exception(f'Could not load action {action} from {namespace}')
            raise exceptions.InvalidDirectiveAction(f'Invalid action {action} for {namespace}')
        responses = action_method(inner_env)
        serial = 0
        async for response in responses:
            serial += 1
            logger.debug(f'Response emitted for {inner_env.message_id}, serial {serial}')
            enveloped_response = envelope.InnerEnvelope.make_response(
                receptor=self.receptor,
                recipient=inner_env.sender,
                payload=response,
                in_response_to=inner_env.message_id,
                serial=serial
            )
            await self.receptor.router.send(enveloped_response)


