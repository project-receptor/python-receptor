import logging
import traceback
import pkg_resources

from . import exceptions
from .messages import envelope
logger = logging.getLogger(__name__)


class WorkManager:
    def __init__(self, receptor):
        self.receptor = receptor
        self.active_work = []

    def load_receptor_worker(self, name):
        entry_points = [x for x in filter(lambda x: x.name == name,
                                          pkg_resources.iter_entry_points("receptor.worker"))]
        if not entry_points:
            raise exceptions.UnknownDirective(f"Error loading directive handlers for {name}")
        return entry_points[0].load()

    def get_capabilities(self):
        return [(x.name, pkg_resources.get_distribution(x.resolve().__package__).version)
                for x in pkg_resources.iter_entry_points('receptor.worker')]

    def get_work(self):
        return self.active_work

    def add_work(self, env):
        self.active_work.append(dict(id=env.message_id,
                                     directive=env.directive,
                                     sender=env.sender))

    def remove_work(self, env):
        for work in self.active_work:
            if env.message_id == work["id"]:
                self.active_work.remove(work)

    async def handle(self, inner_env):
        logger.info(f'Handling work for {inner_env.message_id} as {inner_env.directive}')
        namespace, action = inner_env.directive.split(':', 1)
        serial = 0
        try:
            worker_module = self.load_receptor_worker(namespace)
            try:
                action_method = getattr(worker_module, f'{action}')
            except AttributeError:
                logger.exception(f'Could not load action {action} from {namespace}')
                raise exceptions.InvalidDirectiveAction(f'Invalid action {action} for {namespace}')
            self.add_work(inner_env)
            responses = action_method(inner_env, self.receptor.config.plugins.get("namespace", {}))
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
        except Exception as e:
            serial += 1
            logger.error(f'Error encountered while handling the response, replying with an error message ({e})')
            logger.error(traceback.format_tb(e.__traceback__))
            enveloped_response = envelope.InnerEnvelope.make_response(
                receptor=self.receptor,
                recipient=inner_env.sender,
                payload=str(e),
                in_response_to=inner_env.message_id,
                serial=serial,
                code=1,
            )
            self.remove_work(inner_env)
            await self.receptor.router.send(enveloped_response)

