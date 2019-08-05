import asyncio
import logging

from .protocol import BasicProtocol, create_peer

logger = logging.getLogger(__name__)


def mainloop(receptor, ping_interval=None, loop=asyncio.get_event_loop(), skip_run=False):
    config = receptor.config
    if config.server.server_enable:
        listener = loop.create_server(
            lambda: BasicProtocol(receptor, loop),
            config.server.address, config.server.port, ssl=config.get_server_ssl_context())
        loop.create_task(listener)
        logger.info("Serving on %s:%s", config.server.address, config.server.port)
    for peer in config.peers:
        loop.create_task(create_peer(receptor, loop, *peer.split(":", 1)))
    if ping_interval:
        ping_time = (((int(loop.time()) + 1) // ping_interval) + 1) * ping_interval
        loop.call_at(ping_time, loop.create_task, send_pings_and_reschedule(receptor, loop, ping_time, ping_interval))
    if not skip_run:
        try:
            loop.run_until_complete(receptor.shutdown_handler())
        except KeyboardInterrupt:
            pass
        finally:
            loop.stop()


async def send_pings_and_reschedule(receptor, loop, ping_time, ping_interval):
    logger.debug(f'Scheduling mesh ping.')
    for node_id in receptor.router.get_nodes():
        await receptor.router.ping_node(node_id)
    loop.call_at(ping_time + ping_interval, 
                 loop.create_task, send_pings_and_reschedule(
                     receptor, loop, ping_time + ping_interval, ping_interval))
