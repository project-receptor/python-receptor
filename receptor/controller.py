import asyncio
import datetime
import json
import logging
import socket
import sys
import uuid

from . import protocol
from .messages import envelope

logger = logging.getLogger(__name__)


def send_directive(directive, recipient, payload, socket_path):
    if payload == '-':
        payload = sys.stdin.read()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)
    sock.sendall(f"{recipient}\n{directive}\n{payload}".encode('utf-8') + protocol.DELIM)
    response = b''
    while True:
        part = sock.recv(4096)
        response += part
        if len(part) < 4096:
            # either 0 or end of data
            break
    sys.stdout.buffer.write(response + b"\n")


def mainloop(receptor, address, port, socket_path):
    loop = asyncio.get_event_loop()
    listener = loop.create_server(
        lambda: protocol.BasicProtocol(receptor, loop),
        address, port)
    logger.info("Serving on %s:%s", address, port)
    loop.create_task(listener)
    control_socket = asyncio.start_unix_server(
        ControlSocket(receptor),
        path=socket_path,
        loop=loop
    )
    logger.info(f'Opening control socket on {socket_path}')
    loop.create_task(control_socket)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.stop()


class ControlSocket:
    def __init__(self, receptor):
        self.receptor = receptor

    async def __call__(self, reader, writer):
        try:
            request = await reader.readuntil(protocol.DELIM)
            recipient, directive, payload = request.rstrip(protocol.DELIM).decode('utf8').split('\n', 2)
            message_id = str(uuid.uuid4())
            logger.info(f'{message_id}: Sending {directive} to {recipient}')
            sent_timestamp = datetime.datetime.utcnow()
            inner_env = envelope.InnerEnvelope(
                receptor=self.receptor,
                message_id=message_id,
                sender=self.receptor.node_id,
                recipient=recipient,
                message_type='directive',
                timestamp=sent_timestamp.isoformat(),
                raw_payload=payload,
                directive=directive
            )
            future = asyncio.Future()
            await self.receptor.router.send(inner_env, callback=self.make_response_callback(future))
            logger.info(f'{message_id}: Awaiting response')
            await future
            responded_timestamp = datetime.datetime.utcnow()
            roundtrip_time = responded_timestamp - sent_timestamp
            logger.info(f'{message_id}: Response received - roundtrip time: {roundtrip_time.total_seconds()}s')
            writer.write(future.result().encode('utf8'))
        finally:
            writer.write_eof()
    
    def make_response_callback(self, future):
        async def callback(inner_env):
            future.set_result(
                json.dumps(
                    {
                        'timestamp': inner_env.timestamp,
                        'payload': inner_env.raw_payload
                    }
                )
            )
        return callback

        
