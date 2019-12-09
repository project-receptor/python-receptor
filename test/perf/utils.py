import socket

from pyparsing import alphanums
from pyparsing import Group
from pyparsing import OneOrMore
from pyparsing import Suppress
from pyparsing import Word


class Conn:
    def __init__(self, a, b):
        self.a = a
        self.b = b

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


def read_and_parse_dot(raw_data):
    group = Group(Word(alphanums + "_") + Suppress("--") + Word(alphanums + "_")) + Suppress(";")
    dot = Suppress("graph {") + OneOrMore(group) + Suppress("}")

    data = dot.parseString(raw_data).asList()
    return {Conn(c[0], c[1]) for c in data}


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
