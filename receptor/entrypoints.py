import logging
import time
import asyncio
import sys
import os
import shutil

from prometheus_client import start_http_server

from .controller import Controller
from .messages import Message

logger = logging.getLogger(__name__)


def cleanup_tmpdir(controller):
    try:
        is_ephemeral = controller.receptor.config._is_ephemeral
        base_path = controller.receptor.base_path
    except AttributeError:
        return
    if is_ephemeral:
        try:
            logger.debug(f"Removing temporary directory {base_path}")
            shutil.rmtree(base_path)
        except Exception:
            logger.error(f"Error while removing temporary directory {base_path}", exc_info=True)


def run_as_node(config):
    async def node_keepalive():
        # NOTE: I'm not really happy with this, I'd love to be able to await Peer(node).ping()
        # and then verify the status under a timeout rather than just throw away the result and
        # rely on the connection logic
        for node_id in controller.receptor.router.get_nodes():
            await controller.ping(node_id, expected_response=False)
        absolute_call_time = (((int(controller.loop.time()) + 1) // config.node_keepalive_interval) + 1) * config.node_keepalive_interval
        controller.loop.call_at(absolute_call_time,
                                controller.loop.create_task,
                                node_keepalive())

    try:
        controller = Controller(config)
        logger.info(f'Running as Receptor node with ID: {controller.receptor.node_id}')
        if config.node_stats_enable:
            logger.info(f'Starting stats on port {config.node_stats_port}')
            start_http_server(config.node_stats_port)
        if not config.node_server_disable:
            listen_tasks = controller.enable_server(config.node_listen)
            controller.loop.create_task(controller.exit_on_exceptions_in(listen_tasks))
        for peer in config.node_peers:
            controller.add_peer(peer, ws_extra_headers=config.node_ws_extra_headers)
        if config.node_keepalive_interval > 1:
            controller.loop.create_task(node_keepalive())
        controller.loop.create_task(controller.receptor.watch_expire())
        controller.run()
    finally:
        cleanup_tmpdir(controller)


async def run_oneshot_command(controller, peer, recipient, ws_extra_headers, send_func, read_func):
    add_peer_task = controller.add_peer(peer, ws_extra_headers=ws_extra_headers)
    start_wait = time.time()
    while True:
        if add_peer_task and add_peer_task.done() and not add_peer_task.result():
            print("Connection failed. Exiting.")
            break
        if ((recipient and controller.receptor.router.node_is_known(recipient)) or
                (not recipient and len(controller.receptor.router.get_nodes()) > 0)):
            read_task = controller.loop.create_task(read_func())
            await send_func()
            await read_task
            break
        if (time.time() - start_wait > 5):
            print("Connection timed out. Exiting.")
            if not add_peer_task.done():
                add_peer_task.cancel()
            break
        await asyncio.sleep(0.1)


def run_as_ping(config):
    def ping_iter():
        if config.ping_count:
            for x in range(config.ping_count):
                yield x
        else:
            while True:
                yield 0

    async def ping_entrypoint():
        return await run_oneshot_command(
            controller,
            config.ping_peer,
            config.ping_recipient,
            config.ping_ws_extra_headers,
            send_pings,
            read_responses,
        )

    async def read_responses():
        for _ in ping_iter():
            message = await controller.recv()
            print("{}".format(message.raw_payload))

    async def send_pings():
        for _ in ping_iter():
            await controller.ping(config.ping_recipient)
            await asyncio.sleep(config.ping_delay)

    try:
        logger.info(f"Sending ping to {config.ping_recipient} via {config.ping_peer}.")
        controller = Controller(config)
        controller.run(ping_entrypoint)
    finally:
        cleanup_tmpdir(controller)


def run_as_send(config):
    async def send_entrypoint():
        return await run_oneshot_command(
            controller,
            config.send_peer,
            config.send_recipient,
            config.send_ws_extra_headers,
            send_message,
            read_responses,
        )

    async def send_message():
        msg = Message(config.send_recipient, config.send_directive)
        if config.send_payload == "-":
            msg.data(sys.stdin.buffer.read())
        elif os.path.exists(config.send_payload):
            msg.file(config.send_payload)
        else:
            if isinstance(config.send_payload, str):
                send_payload = config.send_payload.encode()
            else:
                send_payload = config.send_payload
            msg.data(send_payload)
        await controller.send(msg)

    async def read_responses():
        while True:
            message = await controller.recv()
            if message.message_type == 'response':
                logger.debug('Received response message')
                print(f'{message.raw_payload}')
            elif message.message_type == 'eof':
                logger.info('Received EOF')
                if message.code != 0:
                    logger.error(f'EOF was an error result: {message.raw_payload}')
                    print(f'ERROR: {message.raw_payload}')
                break
            else:
                logger.warning(f'Received unknown message type {message.message_type}')
    try:
        logger.info(f'Sending directive {config.send_directive} to {config.send_recipient} via {config.send_peer}')
        controller = Controller(config)
        controller.run(send_entrypoint)
    finally:
        cleanup_tmpdir(controller)


def run_as_status(config):

    async def status_entrypoint():
        return await run_oneshot_command(controller, config.status_peer, None,
                                         config.status_ws_extra_headers, print_status, noop)

    async def print_status():

        # This output should be formatted so as to be parseable as YAML

        r = controller.receptor
        print("Nodes:")
        print("  Myself:", r.router.node_id)
        print("  Others:")
        for node in r.router.get_nodes():
            print("  -", node)
        print()
        print("Route Map:")
        for edge in r.router.get_edges():
            print("-", str(tuple(edge)))
        print()
        print("Known Node Capabilities:")
        for node, node_caps in r.node_capabilities.items():
            print("  ", node, ":", sep="")
            for cap, cap_value in node_caps.items():
                print("    ", cap, ": ", str(cap_value), sep="")

    async def noop():
        return

    try:
        controller = Controller(config)
        controller.run(status_entrypoint)
    finally:
        cleanup_tmpdir(controller)
