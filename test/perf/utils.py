import socket

from pyparsing import alphanums
from pyparsing import Group
from pyparsing import OneOrMore
from pyparsing import Suppress
from pyparsing import Word
from pyparsing import nums
from pyparsing import Optional
from _collections import defaultdict
import logging
import re


logger = logging.getLogger(__name__)

_ports = defaultdict(dict)
_dns_cache = {}
ip_address = re.compile(
    r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}" r"(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
)


class Conn:
    def __init__(self, a, b, cost):
        self.a = a
        self.b = b
        self.cost = cost

    def __eq__(self, other):
        if self.a == other.a and self.b == other.b or self.a == other.b and self.b == other.a:
            return True
        return False

    def __hash__(self):
        enps = [self.a, self.b]
        sorted_enps = sorted(enps)
        return hash(tuple(sorted_enps))

    def __repr__(self):
        return f"{self.a} -- {self.b}"


def read_and_parse_metrics(raw_data):
    token = Suppress("'") + Word(alphanums + "_" + "-") + Suppress("'")
    group = Group(
        Suppress("(") + token + Suppress(",") + token + Suppress(",") + Word(nums) + Suppress(
            ")") + Suppress(Optional(',')))
    dot = Suppress("{") + OneOrMore(group) + Suppress("}")
    data = dot.parseString(raw_data).asList()

    return {Conn(c[0], c[1], c[2]) for c in data}


def random_port(tcp=True):
    """Get a random port number for making a socket

    Args:
        tcp: Return a TCP port number if True, UDP if False

    This may not be reliable at all due to an inherent race condition. This works
    by creating a socket on an ephemeral port, inspecting it to see what port was used,
    closing it, and returning that port number. In the time between closing the socket
    and opening a new one, it's possible for the OS to reopen that port for another purpose.

    In practical testing, this race condition did not result in a failure to (re)open the
    returned port number, making this solution squarely "good enough for now".
    """
    # Port 0 will allocate an ephemeral port
    socktype = socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM
    s = socket.socket(socket.AF_INET, socktype)
    s.bind(("", 0))
    addr, port = s.getsockname()
    s.close()
    return port


def net_check(port, addr="localhost", force=False):
    """Checks the availablility of a port"""
    port = int(port)
    if port not in _ports[addr] or force:
        # First try DNS resolution
        try:

            addr = socket.gethostbyname(addr)

            # Then try to connect to the port
            try:
                socket.create_connection((addr, port), timeout=10)
                _ports[addr][port] = True
            except socket.error:
                logger.exception("failed connection")
                _ports[addr][port] = False
        except Exception as e:
            logger.info(e)
            _ports[addr][port] = False
    return _ports[addr][port]
