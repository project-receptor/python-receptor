import logging
logger = logging.getLogger(__name__)


class Directive:
    def __init__(self, type_, payload):
        self.type_ = type_
        self.payload = payload
