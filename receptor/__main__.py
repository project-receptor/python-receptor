import argparse
import logging
from .events import mainloop

logger = logging.getLogger(__name__)


def main(sys_args=None):
    parser = argparse.ArgumentParser("receptor")
    args = parser.parse_args(sys_args)
    mainloop()
