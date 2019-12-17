import asyncio
import functools
import json
import logging
import struct
import tempfile
import uuid
from enum import IntEnum

logger = logging.getLogger(__name__)

MAX_INT64 = 2 ** 64 - 1


class FileBackedBuffer:

    def __init__(self, dir=None):
        self.length = 0
        self.fp = tempfile.NamedTemporaryFile(dir=dir, delete=False)

    @property
    def name(self):
        return self.fp.name

    def write(self, data):
        written = self.fp.write(data)
        self.length += written
        return written

    def seek(self, offset):
        self.fp.seek(offset)

    def read(self, size=-1):
        return self.fp.read(size)

    def readall(self):
        pos = self.fp.tell()
        try:
            self.fp.seek(0)
            return self.fp.read()
        finally:
            self.fp.seek(pos)

    def __len__(self):
        return self.length


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

    def __iter__(self):
        header_bytes = json.dumps(self.header).encode("utf-8")
        yield Frame.wrap(
            header_bytes,
            type_=Frame.Types.HEADER,
            msg_id=self.msg_id).serialize()
        yield header_bytes
        if self.payload:
            yield Frame.wrap(
                self.payload,
                msg_id=self.msg_id).serialize()
            self.payload.seek(0)
            reader = functools.partial(self.payload.read, size=2 ** 12)
            for chunk in iter(reader, b''):
                yield chunk


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
        self.bb = FileBackedBuffer()
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
        self.to_read -= self.bb.write(data)
        if self.to_read == 0:
            await self.finish()
        if rest:
            await self.handle_frame(rest)

    async def finish(self):
        if self.current_frame.type == Frame.Types.HEADER:
            self.bb.seek(0)
            self.header = json.load(self.bb)
        elif self.current_frame.type == Frame.Types.PAYLOAD:
            await self.q.put(
                FramedMessage(
                    self.current_frame.msg_id, header=self.header, payload=self.bb
                )
            )
            self.header = None
        elif self.current_frame.type == Frame.Types.COMMAND:
            self.bb.seek(0)
            await self.q.put(
                FramedMessage(self.current_frame.msg_id, header=json.load(self.bb))
            )
        else:
            raise Exception("Unknown Frame Type")
        self.to_read = 0
        self.bb = FileBackedBuffer()

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
        return cls.deserialize(data[:Frame.fmt.size]), data[Frame.fmt.size:]

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
