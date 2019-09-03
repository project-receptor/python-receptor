import argparse
import datetime
import logging
import logging.config

from .config import ReceptorConfig
from .receptor import Receptor

logger = logging.getLogger(__name__)


def main(args=None):
    
    config = ReceptorConfig(args)

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
                    'level': 'DEBUG' if config.default_debug else 'INFO',
                },
            },
        }
    )

    config.go()


if __name__ == '__main__':
    # We were run with python -m
    main()
