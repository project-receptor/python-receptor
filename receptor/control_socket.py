import logging
import argparse
import shlex
import asyncio
from .config import ReceptorConfig

logger = logging.getLogger(__name__)


class ArgumentParsingError(Exception):
    pass


class QuietArgParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        self.writer = kwargs.pop("writer", None)
        super().__init__(*args, **kwargs)

    def print_usage(self, file=None):
        if file is None:
            file = self.writer
        self._print_message(self.format_usage(), file)

    def print_help(self, file=None):
        if file is None:
            file = self.writer
        self._print_message(self.format_help(), file)

    def _print_message(self, message, file=None):
        if message:
            if file is None:
                file = self.writer
            if type(file) is asyncio.StreamWriter:
                file.write(message.encode("utf-8"))
            else:
                file.write(message)

    def exit(self, status=0, message=None):
        raise ArgumentParsingError(f"Error {status}: {message}")

    def error(self, message):
        raise ArgumentParsingError(message)


class ControlSocketSession:
    def __init__(self, controller, reader, writer):
        self.controller = controller
        self.receptor = controller.receptor
        self.reader = reader
        self.writer = writer
        self.events = dict()

    async def writestr(self, *args, **kwargs):
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        self.writer.write((sep.join(args) + end).encode("utf-8"))
        await self.writer.drain()

    async def writebytes(self, bytes, crlf=False):
        self.writer.write(bytes)
        if crlf:
            self.writer.write(b"\n")
        await self.writer.drain()

    async def handle_ping_response(self, message):
        if message.payload and not self.writer.is_closing():
            await self.writebytes(message.payload.readall(), crlf=True)
        e = self.events.get(message.header["in_response_to"], None)
        if e:
            e.set()

    async def run_as_ping(self, config):
        try:
            eventlist = list()
            for i in range(config.ping_count):
                msg_id = await self.controller.ping(
                    config.ping_recipient, self.handle_ping_response
                )
                e = asyncio.Event()
                eventlist.append(e)
                self.events[msg_id] = e
                if i < config.ping_count - 1:
                    await asyncio.sleep(config.ping_delay)
            try:
                await asyncio.wait([e.wait() for e in eventlist], timeout=5)
            except asyncio.TimeoutError:
                pass
        except Exception as e:
            await self.writestr(f"Error: {str(e)}")

    async def handle_send_response(self, message):
        if message.payload and not self.writer.is_closing():
            await self.writebytes(message.payload.readall(), crlf=True)
        if message.header.get("eof", False):
            e = self.events.get(message.header["in_response_to"], None)
            if e:
                e.set()

    async def run_as_send(self, config):
        try:
            msg_id = await self.controller.send(
                config.send_payload,
                config.send_recipient,
                config.send_directive,
                self.handle_send_response,
            )
            e = asyncio.Event()
            self.events[msg_id] = e
            await e.wait()
        except Exception as e:
            await self.writestr(f"Error: {str(e)}")

    async def run_as_status(self, config):
        await self.writestr("Nodes:")
        await self.writestr("  Myself:", self.receptor.router.node_id)
        await self.writestr("  Others:")
        for node in self.receptor.router.get_nodes():
            await self.writestr("  -", node)
        await self.writestr()
        await self.writestr("Route Map:")
        for edge in self.receptor.router.get_edges():
            await self.writestr("-", str(tuple(edge)))
        await self.writestr()
        await self.writestr("Known Node Capabilities:")
        for node, node_data in self.receptor.known_nodes.items():
            await self.writestr("  ", node, ":", sep="")
            for cap, cap_value in node_data["capabilities"].items():
                await self.writestr("    ", cap, ": ", str(cap_value), sep="")

    async def session(self):
        logger.debug("Received socket connection")
        while not self.reader.at_eof():
            command = await self.reader.readline()
            if command:
                command = command.decode("utf-8").strip()
                logger.debug(f"Received command {command}")
                try:
                    config = ReceptorConfig(
                        shlex.split(command),
                        parser_class=QuietArgParser,
                        parser_opts=dict(writer=self.writer, add_help=False),
                        context="socket",
                    )
                    entrypoint_name = config.get_entrypoint_name()
                    entrypoint_func = getattr(self, entrypoint_name, None)
                    if entrypoint_func:
                        await entrypoint_func(config)
                    else:
                        await self.writestr(f"Not implemented: {entrypoint_name}")
                except ArgumentParsingError as e:
                    await self.writestr(f"Error: {str(e)}")
                await self.writer.drain()
        logger.debug("Socket connection closed")
        if self.writer.can_write_eof():
            self.writer.write_eof()
        await self.writer.drain()
        self.writer.close()


class ControlSocketServer:
    def __init__(self, controller):
        self.controller = controller

    async def serve_from_socket(self, reader, writer):
        await ControlSocketSession(self.controller, reader, writer).session()
