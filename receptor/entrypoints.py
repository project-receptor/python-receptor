import asyncio
import logging
import shlex

from prometheus_client import start_http_server

from .controller import Controller

logger = logging.getLogger(__name__)


def run_as_node(config):
    async def node_keepalive():
        # NOTE: I'm not really happy with this, I'd love to be able to await Peer(node).ping()
        # and then verify the status under a timeout rather than just throw away the result and
        # rely on the connection logic
        for node_id in controller.receptor.router.get_nodes():
            await controller.ping(node_id, expected_response=False)
        absolute_call_time = (
            ((int(controller.loop.time()) + 1) // config.node_keepalive_interval) + 1
        ) * config.node_keepalive_interval
        controller.loop.call_at(absolute_call_time, controller.loop.create_task, node_keepalive())

    controller = Controller(config)
    logger.info(f"Running as Receptor node with ID: {controller.receptor.node_id}")
    if config.node_stats_enable:
        logger.info(f"Starting stats on port {config.node_stats_port}")
        start_http_server(config.node_stats_port)
    if not config.node_no_listen:
        listen_tasks = controller.enable_server(config.node_listen)
        controller.loop.create_task(controller.exit_on_exceptions_in(listen_tasks))
    if not config.default_no_socket:
        socket_task = controller.enable_control_socket(config.default_socket_path)
        controller.loop.create_task(controller.exit_on_exceptions_in([socket_task]))

    for peer in config.node_peers:
        controller.add_peer(
            peer,
            ws_extra_headers=config.node_ws_extra_headers,
            ws_heartbeat=config.node_ws_heartbeat,
        )
    if config.node_keepalive_interval > 1:
        controller.loop.create_task(node_keepalive())
    controller.loop.create_task(
        controller.receptor.connection_manifest.watch_expire(controller.receptor.buffer_mgr)
    )
    controller.run()


def run_command_via_socket(config, command):
    async def command_client():
        reader, writer = await asyncio.open_unix_connection(config.default_socket_path)
        writer.write(f"{' '.join(shlex.quote(str(x)) for x in command)}\n".encode("utf-8"))
        if writer.can_write_eof():
            writer.write_eof()
        while not reader.at_eof():
            line = await reader.readline()
            print(line.decode("utf-8"), end="")
        writer.close()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(command_client())
    loop.close()


def run_as_ping(config):
    command = ["ping", config.ping_recipient]
    if config.ping_count is not None:
        command.extend(["--count", config.ping_count])
    if config.ping_delay is not None:
        command.extend(["--delay", config.ping_delay])
    run_command_via_socket(config, command)


def run_as_send(config):
    run_command_via_socket(
        config, ["send", config.send_recipient, config.send_directive, config.send_payload]
    )


def run_as_status(config):
    run_command_via_socket(config, ["status"])
