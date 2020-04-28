import asyncio
import concurrent.futures
import datetime
import logging

import pkg_resources

from . import exceptions
from .bridgequeue import BridgeQueue
from .messages.framed import FileBackedBuffer, FramedMessage
from .plugin_utils import BUFFER_PAYLOAD, BYTES_PAYLOAD, FILE_PAYLOAD
from .stats import active_work_gauge, work_counter, work_info

logger = logging.getLogger(__name__)


class WorkManager:
    def __init__(self, receptor):
        self.receptor = receptor
        work_info.info(dict(plugins=str(self.get_capabilities())))
        self.active_work = []
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.receptor.config.default_max_workers
        )

    def load_receptor_worker(self, name):
        entry_points = [
            x
            for x in filter(
                lambda x: x.name == name, pkg_resources.iter_entry_points("receptor.worker")
            )
        ]
        if not entry_points:
            raise exceptions.UnknownDirective(f"Error loading directive handlers for {name}")
        return entry_points[0].load()

    def get_capabilities(self):
        caps = {
            "worker_versions": {
                x.name: pkg_resources.get_distribution(x.resolve().__package__).version
                for x in pkg_resources.iter_entry_points("receptor.worker")
            },
            "max_work_threads": self.receptor.config.default_max_workers,
        }
        if self.receptor.config._is_ephemeral:
            caps["ephemeral"] = True
        return caps

    def get_work(self):
        return self.active_work

    def add_work(self, message):
        work_counter.inc()
        active_work_gauge.inc()
        self.active_work.append(
            dict(
                id=message.msg_id,
                directive=message.header["directive"],
                sender=message.header["sender"],
            )
        )

    def remove_work(self, message):
        for work in self.active_work:
            if message.msg_id == work["id"]:
                active_work_gauge.dec()
                self.active_work.remove(work)

    def resolve_payload_input(self, payload_type, payload):
        if payload_type == BUFFER_PAYLOAD:
            payload.seek(0)
            return payload
        elif payload_type == FILE_PAYLOAD:
            return payload.name
        return payload.readall()

    def get_action_method(self, directive):
        namespace, action = directive.split(":", 1)
        worker_module = self.load_receptor_worker(namespace)
        try:
            action_method = getattr(worker_module, action)
        except AttributeError:
            logger.exception(f"Could not load action {action} from {namespace}")
            raise exceptions.InvalidDirectiveAction(f"Invalid action {action} for {namespace}")
        if not getattr(action_method, "receptor_export", False):
            logger.exception(
                f"""Not allowed to call {action} from {namespace} """
                """because it is not marked for export"""
            )
            raise exceptions.InvalidDirectiveAction(
                f"Access denied calling {action} for {namespace}"
            )
        return action_method, namespace

    async def handle(self, message):
        directive = message.header["directive"]
        logger.info(f"Handling work for {message.msg_id} as {directive}")
        try:
            serial = 0
            eof_response = None
            action_method, namespace = self.get_action_method(directive)
            payload_input_type = getattr(action_method, "payload_type", BYTES_PAYLOAD)

            self.add_work(message)
            response_queue = BridgeQueue()
            asyncio.wrap_future(
                self.thread_pool.submit(
                    action_method,
                    self.resolve_payload_input(payload_input_type, message.payload),
                    self.receptor.config.plugins.get(namespace, {}),
                    response_queue,
                )
            ).add_done_callback(lambda fut: response_queue.close())

            async for response in response_queue:
                serial += 1
                logger.debug(f"Response emitted for {message.msg_id}, serial {serial}")
                response_message = FramedMessage(
                    header=dict(
                        recipient=message.header["sender"],
                        in_response_to=message.msg_id,
                        serial=serial,
                        timestamp=datetime.datetime.utcnow(),
                    ),
                    payload=FileBackedBuffer.from_data(response),
                )
                await self.receptor.router.send(response_message)

        except Exception as e:
            logger.exception(
                """Error encountered while handling the response, replying with an error message"""
            )
            eof_response = FramedMessage(
                header=dict(
                    recipient=message.header["sender"],
                    in_response_to=message.msg_id,
                    serial=serial + 1,
                    code=1,
                    timestamp=datetime.datetime.utcnow(),
                    eof=True,
                ),
                payload=FileBackedBuffer.from_data(str(e)),
            )
        self.remove_work(message)

        if eof_response is None:
            eof_response = FramedMessage(
                header=dict(
                    recipient=message.header["sender"],
                    in_response_to=message.msg_id,
                    serial=serial + 1,
                    code=0,
                    timestamp=datetime.datetime.utcnow(),
                    eof=True,
                )
            )
        await self.receptor.router.send(eof_response)
