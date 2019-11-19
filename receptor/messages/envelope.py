import asyncio
import base64
import datetime
import itertools
import json
import logging
import time
import uuid
from struct import pack, unpack

logger = logging.getLogger(__name__)

MAX_INT64 = (2 ** 64 - 1)


class FramedBuffer:
    """
    A buffer that accumulates frames and bytes to produce a header and a
    payload.

    This buffer assumes that an entire message (denoted by msg_id) will be
    sent before another message is sent.
    """
    def __init__(self, loop=None):
        self.q = asyncio.Queue(loop=loop)
        self.header = None
        self.bb = bytearray()
        self.current_frame = None
        self.to_read = 0

    async def put(self, data):
        if not self.to_read:
            return await self.handle_frame(data)
        await self.consume(data)
    
    async def handle_frame(self, data):
        self.current_frame, rest = Frame.from_data(data)
        if self.current_frame.type in (Frame.START_MSG, Frame.PAYLOAD):
            self.to_read = self.current_frame.length
            await self.consume(rest)
        else:
            raise Exception("Unknown Frame Type")

    async def consume(self, data):
        self.to_read -= len(data)
        self.bb += data
        if self.to_read == 0:
            await self.finish()

    async def finish(self):
        if self.current_frame.type == Frame.START_MSG:
            self.header = Header(**json.loads(self.bb))
        elif self.current_frame.type == Frame.PAYLOAD:
            await self.q.put((self.header, self.bb))
            self.header = None
        self.to_read = 0
        self.bb = bytearray()

    async def get(self):
        return await self.q.get()


class Frame:
    START_MSG = 0
    PAYLOAD = 1
    FINISH = 2

    def __init__(self, type_, version, length, msg_id, id_):
        self.type = type_
        self.version = version
        self.length = length
        self.msg_id = msg_id
        self.id = id_

    def serialize(self):
        high, low = ((self.msg_id >> 64) & MAX_INT64, self.msg_id & MAX_INT64)
        return b''.join([
            pack("ccIi", chr(self.type).encode("ascii"), chr(self.version).encode("ascii"), self.id, self.length),
            pack(">QQ", high, low),
        ])

    @classmethod
    def deserialize(cls, buf):
        t, v, i, length = unpack("ccIi", buf[0:12])
        hi, lo = unpack(">QQ", buf[12:])
        msg_id = (hi << 64) | lo
        return cls(ord(t), ord(v), length, msg_id, i)

    @classmethod
    def from_data(cls, data):
        return cls.deserialize(data[:28]), data[28:]


class Header:
    def __init__(self, sender, recipient, route_list):
        self.sender = sender
        self.recipient = recipient
        self.route_list = route_list

    def serialize(self):
        return json.dumps({"sender": self.sender, "recipient": self.recipient, "route_list": self.route_list}).encode("utf-8")

    def __repr__(self):
        return f"Header: {self.sender}, {self.recipient}, {self.route_list}"

    def __eq__(self, other):
        return (self.sender, self.recipient, self.route_list) == (other.sender, other.recipient, other.route_list)


def gen_chunks(buffer, header, msg_id=None, chunksize=2 ** 8):
    if msg_id is None:
        msg_id = uuid.uuid4().int
    seq = itertools.count()
    buf = bytearray(chunksize)
    bv = memoryview(buf)
    header = header.serialize()
    yield Frame(Frame.START_MSG, 1, len(header), msg_id, next(seq)).serialize() + header
    bytes_read = buffer.readinto(buf)
    while bytes_read:
        f = Frame(Frame.PAYLOAD, 1, bytes_read, msg_id, next(seq)).serialize()
        if bytes_read == chunksize:
            yield f + bv.tobytes()
        else:
            yield f + bv[:bytes_read].tobytes()
        bytes_read = buffer.readinto(buf)


class OuterEnvelope:
    def __init__(self, frame_id, sender, recipient, route_list, inner):
        self.frame_id = frame_id
        self.sender = sender
        self.recipient = recipient
        self.route_list = route_list
        self.inner = inner
        self.inner_obj = None

    async def deserialize_inner(self, receptor):
        self.inner_obj = await InnerEnvelope.deserialize(receptor, self.inner)

    @classmethod
    def from_raw(cls, raw):
        doc = json.loads(raw)
        return cls(**doc)
    
    def serialize(self):
        return json.dumps(dict(
            frame_id=self.frame_id,
            sender=self.sender,
            recipient=self.recipient,
            route_list=self.route_list,
            inner=self.inner
        ))


class InnerEnvelope:
    def __init__(self, receptor, message_id, sender, recipient, message_type, timestamp,
                 raw_payload, directive=None, in_response_to=None, ttl=None, serial=1,
                 code=0, expire_time_delta=300):
        self.receptor = receptor
        self.message_id = message_id
        self.sender = sender
        self.recipient = recipient
        self.message_type = message_type # 'directive' or 'response'
        self.timestamp = timestamp # ISO format
        self.raw_payload = raw_payload
        self.directive = directive # None if response, 'namespace:action' if not
        self.in_response_to = in_response_to # None if directive, a message_id if not
        self.ttl = ttl # Optional
        if not expire_time_delta:
            self.expire_time = None
        self.expire_time = time.time() + expire_time_delta
        self.serial = serial # serial index of responses
        self.code = code # optional code indicating an error

    @classmethod
    async def deserialize(cls, receptor, msg):
        payload = await receptor.config.components_security_manager.verify_msg(msg)
        # validate msg
        # msg+sig
        return cls(receptor=receptor, **json.loads(payload))

    @classmethod
    def make_response(cls, receptor, recipient, payload, in_response_to, serial, ttl=None, code=0):
        if isinstance(payload, bytes):
            encoded_payload = base64.encodebytes(payload)
        else:
            encoded_payload = payload
        return cls(
            receptor=receptor,
            message_id=str(uuid.uuid4()),
            sender=receptor.node_id,
            recipient=recipient,
            message_type='response',
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
