import base64
import datetime
import io
import json
import logging
import time
import uuid

from ..exceptions import ReceptorRuntimeError

logger = logging.getLogger(__name__)


class Message:

    __slots__ = ("fd", "recipient", "directive")

    def __init__(self, recipient, directive):
        self.fd = io.BytesIO()
        self.recipient = recipient
        self.directive = directive

    def open(self):
        self.fd.seek(0)
        return self.fd

    def file(self, path):
        self.fd = open(path, 'r+b')

    def buffer(self, buffered_io):
        if not isinstance(buffered_io, io.BytesIO):
            raise ReceptorRuntimeError("buffer must be of type io.BytesIO")
        self.fd = buffered_io

    def data(self, raw_data):
        if isinstance(raw_data, str):
            raw_data = raw_data.encode()
        self.fd.write(raw_data)


class Inner:
    def __init__(
        self,
        receptor,
        message_id,
        sender,
        recipient,
        message_type,
        timestamp,
        raw_payload,
        directive=None,
        in_response_to=None,
        ttl=None,
        serial=1,
        code=0,
        expire_time_delta=300,
    ):
        self.receptor = receptor
        self.message_id = message_id
        self.sender = sender
        self.recipient = recipient
        self.message_type = message_type  # 'directive', 'response' or 'eof'
        self.timestamp = timestamp  # ISO format
        self.raw_payload = raw_payload
        self.directive = directive  # None if response, 'namespace:action' if not
        self.in_response_to = in_response_to  # None if directive, a message_id if not
        self.ttl = ttl  # Optional
        if not expire_time_delta:
            self.expire_time = None
        self.expire_time = time.time() + expire_time_delta
        self.serial = serial  # serial index of responses
        self.code = code  # optional code indicating an error

    @classmethod
    async def deserialize(cls, receptor, msg):
        payload = await receptor.config.components_security_manager.verify_msg(msg)
        # validate msg
        # msg+sig
        return cls(receptor=receptor, **json.loads(payload))

    @classmethod
    def make_response(
        cls, receptor, recipient, payload, in_response_to, serial, ttl=None,
        code=0, message_type="response"
    ):
        if isinstance(payload, bytes):
            encoded_payload = base64.encodebytes(payload)
        else:
            encoded_payload = payload
        return cls(
            receptor=receptor,
            message_id=str(uuid.uuid4()),
            sender=receptor.node_id,
            recipient=recipient,
            message_type=message_type,
            timestamp=datetime.datetime.utcnow().isoformat(),
            raw_payload=encoded_payload,
            directive=None,
            in_response_to=in_response_to,
            ttl=ttl,
            serial=serial,
            code=code,
        )

    def sign_and_serialize(self):
        return self.receptor.config.components_security_manager.sign_response(self)
