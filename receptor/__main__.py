import asyncio
import logging
import logging.config
import signal
import sys
from collections import deque

from .config import ReceptorConfig
from .diagnostics import log_buffer
from .logstash_formatter.logstash import LogstashFormatter

logger = logging.getLogger(__name__)


def main(args=None):

    try:
        config = ReceptorConfig(args)
    except Exception as e:
        logger.error("An error occured while validating the configuration options:\n%s" % (str(e),))
        sys.exit(1)

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "simple": {
                    "format": "{levelname} {asctime} {node_id} {module} {message}",
                    "style": "{",
                },
                "structured": {"()": LogstashFormatter},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "structured"
                    if config.default_logging_format == "structured"
                    else "simple",
                }
            },
            "loggers": {
                "receptor": {
                    "handlers": ["console"],
                    "level": "DEBUG" if config.default_debug else "WARN",
                }
            },
        }
    )

    def _f(record):
        record.node_id = config.default_node_id
        if record.levelno == logging.ERROR:
            log_buffer.appendleft(record)
        return True

    for h in logging.getLogger("receptor").handlers:
        h.addFilter(_f)

    def dump_stacks(signum, frame):
        for t in asyncio.Task.all_tasks():
            t.print_stack(file=sys.stderr)

    signal.signal(signal.SIGHUP, dump_stacks)

    try:
        config.go()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("main: an error occured while running receptor")
        sys.exit(1)


if __name__ == "__main__":
    # We were run with python -m
    main()
