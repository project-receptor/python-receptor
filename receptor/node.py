import asyncio
import logging

from .protocol import BasicProtocol, create_peer

logger = logging.getLogger(__name__)


# FIXME: ping_interval is in the config, it shouldn't need to be passed as an arg here
def mainloop(receptor, ping_interval=None, loop=asyncio.get_event_loop(), skip_run=False):
    config = receptor.config
    if not config.node_server_disable:
        listener = loop.create_server(
            lambda: BasicProtocol(receptor, loop),
            config.node_listen_address, config.node_listen_port, ssl=config.get_server_ssl_context())
        loop.create_task(listener)
        logger.info("Serving on %s:%s", config.node_listen_address, config.node_listen_port)
    for peer in config.node_peers:
        loop.create_task(create_peer(receptor, loop, *peer.strip().split(":", 1)))
    if ping_interval > 0:
        ping_time = (((int(loop.time()) + 1) // ping_interval) + 1) * ping_interval
        loop.call_at(ping_time, loop.create_task, send_pings_and_reschedule(receptor, loop, ping_time, ping_interval))
    loop.create_task(receptor.watch_expire())
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
