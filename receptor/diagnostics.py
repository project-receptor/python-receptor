import asyncio
import logging
import os
from collections import deque
from datetime import datetime

from . import fileio, serde
from .logstash_formatter.logstash import LogstashFormatter

logger = logging.getLogger(__name__)

log_buffer = deque(maxlen=10)
fmt = LogstashFormatter()


async def status(receptor_object):
    path = os.path.join(receptor_object.base_path, "diagnostics.json")
    doc = {}
    doc["config"] = receptor_object.config._parsed_args.__dict__
    while True:
        doc["datetime"] = datetime.utcnow().isoformat()
        doc["recent_errors"] = list(fmt._record_to_dict(r) for r in log_buffer)
        doc["connections"] = receptor_object.connections
        try:
            await fileio.write(path, serde.force_dumps(doc), mode="w")
        except Exception:
            logger.exception("failed to dump diagnostic data")
        await asyncio.sleep(30)
