import asyncio
import time

import click

from receptor import Controller
from receptor import ReceptorConfig


def run_as_ping(config):
    def ping_iter():
        if config.ping_count:
            for x in range(config.ping_count):
                yield x
        else:
            while True:
                yield 0

    async def ping_entrypoint():
        read_task = controller.loop.create_task(read_responses())
        await controller.add_peer(config.ping_peer)
        start_wait = time.time()
        while not controller.receptor.router.node_is_known(config.ping_recipient) and (
            time.time() - start_wait < 5
        ):
            await asyncio.sleep(0.1)
        await send_pings()
        await read_task

    async def read_responses():
        for _ in ping_iter():
            payload = await controller.recv()
            print("{}".format(payload))

    async def send_pings():
        for _ in ping_iter():
            await controller.ping(config.ping_recipient)
            await asyncio.sleep(config.ping_delay)

    print(f"Sending ping to {config.ping_recipient} via {config.ping_peer}.")
    controller = Controller(config)
    # controller.loop = asyncio.get_event_loop()
    return controller.run(ping_entrypoint)


@click.command("ping")
@click.option("--data-path", default="/tmp/receptor")
@click.option("--peer", default="receptor://127.0.0.1:8889")
@click.option("--id", default="node1")
@click.option("--node-id", default="ping-node")
@click.option("--count", default=10)
def ping(data_path, peer, id, node_id, count):
    config = ReceptorConfig(
        ["-d", data_path, "--node-id", node_id, "ping", "--peer", peer, id, "--count", str(count)]
    )
    run_as_ping(config)


if __name__ == "__main__":
    ping()
