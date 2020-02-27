import logging
import traceback
import datetime
import pkg_resources

from . import exceptions
from .messages.framed import FramedMessage, FileBackedBuffer
from .stats import active_work_gauge, work_counter, work_info

import concurrent.futures
import queue
import asyncio

logger = logging.getLogger(__name__)


class WorkManager:
    def __init__(self, receptor):
        self.receptor = receptor
        work_info.info(dict(plugins=str(self.get_capabilities())))
        self.active_work = []
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=self.receptor.config.default_max_workers)

    def load_receptor_worker(self, name):
        entry_points = [x for x in filter(lambda x: x.name == name,
                                          pkg_resources.iter_entry_points("receptor.worker"))]
        if not entry_points:
            raise exceptions.UnknownDirective(f"Error loading directive handlers for {name}")
        return entry_points[0].load()

    def get_capabilities(self):
        caps = {
            'worker_versions': {
                x.name: pkg_resources.get_distribution(x.resolve().__package__).version
                for x in pkg_resources.iter_entry_points('receptor.worker')
                },
            'max_work_threads': self.receptor.config.default_max_workers,
        }
        if self.receptor.config._is_ephemeral:
            caps['ephemeral'] = True
        return caps

    def get_work(self):
        return self.active_work

    def add_work(self, message):
        work_counter.inc()
        active_work_gauge.inc()
        self.active_work.append(dict(id=message.header["message_id"],
                                     directive=message.header["directive"],
                                     sender=message.header["sender"]))

    def remove_work(self, message):
        for work in self.active_work:
            if message.header["message_id"] == work["id"]:
                active_work_gauge.dec()
                self.active_work.remove(work)

    async def handle(self, message):
        logger.info(f'Handling work for {message.header["message_id"]} as {message.header["directive"]}')
        namespace, action = message.header["directive"].split(':', 1)
        serial = 0
        eof_response = None
        try:
            worker_module = self.load_receptor_worker(namespace)
            try:
                action_method = getattr(worker_module, f'{action}')
            except AttributeError:
                logger.exception(f'Could not load action {action} from {namespace}')
                raise exceptions.InvalidDirectiveAction(f'Invalid action {action} for {namespace}')
            if not getattr(action_method, "receptor_export", False):
                logger.exception(f'Not allowed to call {action} from {namespace} because it is not marked for export')
                raise exceptions.InvalidDirectiveAction(f'Access denied calling {action} for {namespace}')

            self.add_work(message)
            response_queue = queue.Queue()
            work_exec = self.thread_pool.submit(action_method, message, self.receptor.config.plugins.get(namespace, {}), response_queue)
            while True:
                # Collect 'done' status here so we drain the response queue
                # after the work is complete
                is_done = work_exec.done()
                while True:
                    try:
                        response = response_queue.get(False)
                        serial += 1
                        logger.debug(f'Response emitted for {message.header["message_id"]}, serial {serial}')
                        message = FramedMessage(
                            header=dict(
                                recipient=message.header["sender"],
                                in_response_to=message.header["message_id"],
                                serial=serial,
                                timestamp=datetime.datetime.now().isoformat()
                            ),
                            payload=FileBackedBuffer.from_data(response)
                        )
                        await self.receptor.router.send(message)
                    except queue.Empty:
                        break
                if is_done:
                    # Calling result() will raise any exceptions from the worker thread, on this thread
                    work_exec.result()
                    break
                await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f'Error encountered while handling the response, replying with an error message ({e})')
            logger.error(traceback.format_tb(e.__traceback__))
            eof_response = FramedMessage(
                header=dict(
                    recipient=message.header["sender"],
                    in_response_to=message.header["message_id"],
                    serial=serial+1,
                    code=1,
                    timestamp=datetime.datetime.now().isoformat(),
                    message_type="eof"  # TODO: Not message type (eof=True|False?)
                ),
                payload=FileBackedBuffer.from_data(str(e))
            )
        self.remove_work(message)

        if eof_response is None:
            eof_response = FramedMessage(
                header=dict(
                    recipient=message.header["sender"],
                    in_response_to=message.header["message_id"],
                    serial=serial+1,
                    code=0,
                    timestamp=datetime.datetime.now().isoformat(),
                    message_type="eof"  # TODO: Not message type
                )
            )
        await self.receptor.router.send(eof_response)
        if self.receptor.is_ephemeral(message.header["sender"]):
            self.receptor.remove_connection_by_id(message.header["sender"])
