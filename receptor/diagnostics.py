import asyncio
import logging
import os
from collections import deque
from datetime import datetime
import signal

from . import fileio, serde
from .logstash_formatter.logstash import LogstashFormatter

logger = logging.getLogger(__name__)

log_buffer = deque(maxlen=10)
fmt = LogstashFormatter()
trigger = asyncio.Event()

signal.signal(signal.SIGHUP, lambda n, h: trigger.set())


async def status(receptor_object):
    path = os.path.join(receptor_object.base_path, "diagnostics.json")
    doc = {}
    doc["config"] = receptor_object.config._parsed_args.__dict__
    while True:
        trigger.clear()
        doc["datetime"] = datetime.utcnow().isoformat()
        doc["recent_errors"] = list(fmt._record_to_dict(r) for r in log_buffer)
        doc["connections"] = receptor_object.connections
        doc["routes"] = receptor_object.router
        doc["tasks"] = list(asyncio.Task.all_tasks())
        try:
            await fileio.write(path, serde.force_dumps(doc), mode="w")
        except Exception:
            logger.exception("failed to dump diagnostic data")

        # run every 30 seconds, or when triggered
        try:
            await asyncio.wait_for(trigger.wait(), 30)
        except asyncio.TimeoutError:
            pass
