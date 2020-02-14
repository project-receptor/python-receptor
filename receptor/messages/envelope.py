import asyncio
import base64
import datetime
import json
import logging
import struct
import time
import uuid
import io
from enum import IntEnum

from ..exceptions import ReceptorRuntimeError

logger = logging.getLogger(__name__)

MAX_INT64 = 2 ** 64 - 1


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


class FramedMessage:
    """
    A complete, two-part message.
    """

    __slots__ = ("msg_id", "header", "payload")

    def __init__(self, msg_id=None, header=None, payload=None):
        if msg_id is None:
            msg_id = uuid.uuid4().int
        self.msg_id = msg_id
        self.header = header
        self.payload = payload

    def __repr__(self):
        return f"FramedMessage(msg_id={self.msg_id}, header={self.header}, payload={self.payload})"

    def serialize(self):
        h = json.dumps(self.header).encode("utf-8")
        return b"".join(
            [
                Frame.wrap(h, type_=Frame.Types.HEADER, msg_id=self.msg_id).serialize(),
                h,
                Frame.wrap(self.payload, msg_id=self.msg_id).serialize(),
                self.payload,
            ]
        )


class CommandMessage(FramedMessage):
    """
    A complete, single part message, meant to encapsulate point to point
    commands or naive broadcasts.
    """

    def serialize(self):
        h = json.dumps(self.header).encode("utf-8")
        return b"".join(
            [
                Frame.wrap(
                    h, type_=Frame.Types.COMMAND, msg_id=self.msg_id
                ).serialize(),
                h,
            ]
        )


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
        self.framebuffer = bytearray()
        self.bb = bytearray()
        self.current_frame = None
        self.to_read = 0

    async def put(self, data):
        if not self.to_read:
            return await self.handle_frame(data)
        await self.consume(data)

    async def handle_frame(self, data):
        try:
            self.framebuffer += data
            frame, rest = Frame.from_data(self.framebuffer)
        except struct.error:
            return  # We don't have enough data yet
        else:
            self.framebuffer = bytearray()

        if frame.type not in Frame.Types:
            raise Exception("Unknown Frame Type")

        self.current_frame = frame
        self.to_read = self.current_frame.length
        await self.consume(rest)

    async def consume(self, data):
        data, rest = data[:self.to_read], data[self.to_read:]
        self.to_read -= len(data)
        self.bb += data
        if self.to_read == 0:
            await self.finish()
        if rest:
            await self.handle_frame(rest)

    async def finish(self):
        if self.current_frame.type == Frame.Types.HEADER:
            self.header = json.loads(self.bb)
        elif self.current_frame.type == Frame.Types.PAYLOAD:
            await self.q.put(
                FramedMessage(
                    self.current_frame.msg_id, header=self.header, payload=self.bb
                )
            )
            self.header = None
        elif self.current_frame.type == Frame.Types.COMMAND:
            await self.q.put(
                FramedMessage(self.current_frame.msg_id, header=json.loads(self.bb))
            )
        else:
            raise Exception("Unknown Frame Type")
        self.to_read = 0
        self.bb = bytearray()

    async def get(self):
        return await self.q.get()

    def get_nowait(self):
        return self.q.get_nowait()


class Frame:
    """
    A Frame represents the minimal metadata about a transmission.

    Usually you should not create one directly, but rather use the
    FramedMessage or CommandMessage classes.
    """

    class Types(IntEnum):
        HEADER = 0
        PAYLOAD = 1
        COMMAND = 2

    fmt = struct.Struct(">ccIIQQ")

    __slots__ = ("type", "version", "length", "msg_id", "id")

    def __init__(self, type_, version, length, msg_id, id_):
        self.type = type_
        self.version = version
        self.length = length
        self.msg_id = msg_id
        self.id = id_

    def __repr__(self):
        return f"Frame({self.type}, {self.version}, {self.length}, {self.msg_id}, {self.id})"

    def serialize(self):
        return self.fmt.pack(
            bytes([self.type]),
            bytes([self.version]),
            self.id,
            self.length,
            *split_uuid(self.msg_id),
        )

    @classmethod
    def deserialize(cls, buf):
        t, v, i, length, hi, lo = Frame.fmt.unpack(buf)
        msg_id = join_uuid(hi, lo)
        return cls(Frame.Types(ord(t)), ord(v), length, msg_id, i)

    @classmethod
    def from_data(cls, data):
        return cls.deserialize(data[: Frame.fmt.size]), data[Frame.fmt.size:]

    @classmethod
    def wrap(cls, data, type_=Types.PAYLOAD, msg_id=None):
        """
        Returns a frame for the passed data.
        """
        if not msg_id:
            msg_id = uuid.uuid4().int

        return cls(type_, 1, len(data), msg_id, 1)


def split_uuid(data):
    "Splits a 128 bit int into two 64 bit words for binary encoding"
    return ((data >> 64) & MAX_INT64, data & MAX_INT64)


def join_uuid(hi, lo):
    "Joins two 64 bit words into a 128bit int from binary encoding"
    return (hi << 64) | lo


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
