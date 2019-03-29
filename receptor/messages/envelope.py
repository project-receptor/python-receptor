import base64
import datetime
import json
import logging
import uuid

import receptor

logger = logging.getLogger(__name__)


class OuterEnvelope:
    def __init__(self, frame_id, sender, recipient, route_list, inner):
        self.frame_id = frame_id
        self.sender = sender
        self.recipient = recipient
        self.route_list = route_list
        self.inner = inner
        self.inner_obj = None

    async def deserialize_inner(self):
        self.inner = await InnerEnvelope.deserialize(self.inner)

    @classmethod
    def from_raw(cls, raw):
        doc = json.loads(raw)
        return cls(**doc)


class InnerEnvelope:
    def __init__(self, message_id, sender, recipient, message_type, timestamp,
                 raw_payload, directive=None, in_response_to=None, ttl=None,
                 serial=1):
        self.message_id = message_id
        self.sender = sender
        self.recipient = recipient
        self.message_type = message_type # 'directive' or 'response'
        self.timestamp = timestamp # ISO format
        self.raw_payload = raw_payload
        self.directive = directive # None if response, 'namespace:action' if not
        self.in_response_to = in_response_to # None if directive, a message_id if not
        self.ttl = ttl # Optional
        self.serial = serial # serial index of responses

    @classmethod
    async def deserialize(cls, msg):
        payload = await receptor.config.security_manager.validate_msg(msg)
        # validate msg
        # msg+sig
        return cls(**json.loads(payload))

    @classmethod
    def make_response(cls, recipient, payload, in_response_to, serial, ttl=None):
        if isinstance(payload, bytes):
            encoded_payload = base64.encodebytes(payload)
        else:
            encoded_payload = payload
        return cls(
            message_id=str(uuid.uuid4()),
            sender=receptor.get_node_id(),
            recipient=recipient,
            message_type='response',
            timestamp=datetime.datetime.utcnow().isoformat(),
            raw_payload=encoded_payload,
            directive=None,
            in_response_to=in_response_to,
            ttl=ttl,
            serial=serial
        )

    def sign_and_serialize(self):
        return receptor.config.components.security_manager.sign_response(self)
