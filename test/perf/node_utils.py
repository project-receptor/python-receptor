import sys
from test.perf.affinity import Mesh
from time import sleep

import click
import requests
from prometheus_client.parser import text_string_to_metric_families

DEBUG = False

RECEPTOR_METRICS = (
    "active_work",
    "connected_peers",
    "incoming_messages",
    "route_events",
    "work_events",
)


def do_loop(mesh):
    mesh.start()
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        mesh.stop()


@click.group(help="Helper commands for application")
def main():
    pass


@main.command("random")
@click.option("--socket-path", default=None)
@click.option("--debug", is_flag=True, default=False)
@click.option("--controller-port", help="Chooses Controller port", default=8888)
@click.option("--node-count", help="Choose number of nodes", default=10)
@click.option("--max-conn-count", help="Choose max number of connections per node", default=2)
@click.option("--profile", is_flag=True, default=False)
def randomize(controller_port, node_count, max_conn_count, debug, profile, socket_path):
    if debug:
        global DEBUG
        DEBUG = True

    mesh = Mesh.generate_random_mesh(
        controller_port, node_count, max_conn_count, profile, socket_path
    )
    print(mesh)
    do_loop(mesh)


@main.command("flat")
@click.option("--socket-path", default=None)
@click.option("--debug", is_flag=True, default=False)
@click.option("--controller-port", help="Chooses Controller port", default=8888)
@click.option("--node-count", help="Choose number of nodes", default=10)
@click.option("--profile", is_flag=True, default=False)
def flat(controller_port, node_count, debug, profile, socket_path):
    if debug:
        global DEBUG
        DEBUG = True

    mesh = Mesh.generate_flat_mesh(controller_port, node_count, profile, socket_path)
    print(mesh)
    do_loop(mesh)


@main.command("file")
@click.option("--debug", is_flag=True, default=False)
@click.argument("filename", type=click.File("r"))
def file(filename, debug):
    mesh = Mesh.load_mesh_from_file(filename)
    do_loop(mesh)


@main.command("ping")
@click.option("--validate", default=None)
@click.option("--count", default=10)
@click.option("--socket-path", default=None)
@click.argument("filename", type=click.File("r"))
def ping(filename, count, validate, socket_path):
    mesh = Mesh.load_mesh_from_file(filename)

    results = mesh.ping(count, socket_path=socket_path)
    Mesh.validate_ping_results(results, validate)


@main.command("check-stats")
@click.option("--debug", is_flag=True, default=False)
@click.option("--profile", is_flag=True, default=False)
@click.argument("filename", type=click.File("r"))
def check_stats(filename, debug, profile):
    mesh = Mesh.load_mesh_from_file(filename)
    failures = []

    for node in mesh.nodes.values():
        if not node.stats_enable:
            continue
        stats = requests.get(f"http://localhost:{node.stats_port}/metrics")
        metrics = {
            metric.name: metric
            for metric in text_string_to_metric_families(stats.text)
            if metric.name in RECEPTOR_METRICS
        }
        expected_connected_peers = len(
            [n for n in mesh.nodes.values() if node.name in n.connections]
        ) + len(node.connections)
        connected_peers = metrics["connected_peers"].samples[0].value
        if expected_connected_peers != connected_peers:
            failures.append(
                f"Node '{node.name}' was expected to have "
                f"{expected_connected_peers} connections, but it reported to "
                f" have {connected_peers}"
            )
    if failures:
        print("\n".join(failures))
        sys.exit(127)


if __name__ == "__main__":
    main()
