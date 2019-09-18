import argparse
import datetime
import logging
import logging.config
import sys

from .config import ReceptorConfig
from .receptor import Receptor

logger = logging.getLogger(__name__)


def main(args=None):
    
    try:
        config = ReceptorConfig(args)
    except Exception as e:
        logger.error("An error occured while validating the configuration options:\n%s" % (str(e),))
        sys.exit(1)

    logging.config.dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'verbose': {
                    'format': '{levelname} {asctime} {module} {message}',
                    'style': '{',
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'verbose'
                },
            },
            'loggers': {
                'receptor': {
                    'handlers': ['console'],
                    'level': 'DEBUG' if config.default_debug else 'WARN',
                },
            },
        }
    )

    try:
        config.go()
    except Exception as e:
        logger.error("An error occured while running receptor:\n%s" % (str(e),))
        sys.exit(1)


if __name__ == '__main__':
    # We were run with python -m
    main()
