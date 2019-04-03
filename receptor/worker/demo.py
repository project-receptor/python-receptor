import logging
import subprocess

logger = logging.getLogger(__name__)


async def do_uptime(inner_env):
    yield subprocess.check_output('uptime').decode('utf8')
