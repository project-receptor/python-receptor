import random
import socket
import subprocess
import sys
import time
from collections import defaultdict
from collections import namedtuple
from time import sleep

import click
import yaml


DEBUG = False


def random_port(tcp=True):
    """Get a random port number for making a socket

    Args:
        tcp: Return a TCP port number if True, UDP if False

    This may not be reliable at all due to an inherent race condition. This works
    by creating a socket on an ephemeral port, inspecting it to see what port was used,
    closing it, and returning that port number. In the time between closing the socket
    and opening a new one, it's possible for the OS to reopen that port for another purpose.

    In practical testing, this race condition did not result in a failure to (re)open the
    returned port number, making this solution squarely "good enough for now".
    """
    # Port 0 will allocate an ephemeral port
    socktype = socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM
    s = socket.socket(socket.AF_INET, socktype)
    s.bind(("", 0))
    addr, port = s.getsockname()
    s.close()
    return port


procs = []


Node = namedtuple("Node", ["name", "controller", "listen_port", "connections"])


def generate_random_mesh(controller_port, node_count, conn_method):
    a = {"controller": Node("controller", True, controller_port, [])}

    for i in range(node_count):
        a[f"node{i}"] = Node(f"node{i}", False, random_port(), [])

    for k, node in a.items():
        if node.controller:
            continue
        else:
            node.connections.extend(conn_method(a, node))
    return a


def do_it(topology, profile=False):
    with open("last-topology.yaml", "w") as f:
        data = {"nodes": {}}
        for node, node_data in topology.items():
            data["nodes"][node] = {
                "name": node_data.name,
                "listen_port": node_data.listen_port if node_data.controller else None,
                "controller": node_data.controller,
                "connections": node_data.connections,
            }
        yaml.dump(data, f)
    with open("last-topology_graph.dot", "w") as f:
        f.write("graph {")
        for node, node_data in topology.items():
            for conn in node_data.connections:
                f.write(f"{node} -- {conn}; ")
        f.write("}")

    with open("command-log.log", "w") as f:
        for k, node in topology.items():

            if profile:
                start = [
                    "python",
                    "-m",
                    "cProfile",
                    "-o",
                    f"{node.name}.prof",
                    "-m",
                    "receptor.__main__",
                ]
            else:
                start = ["receptor"]

            if node.controller:
                if not DEBUG:
                    starter = start[:]
                    starter.extend(
                        [
                            "--debug",
                            "-d",
                            "/tmp/receptor",
                            "--node-id",
                            "controller",
                            "controller",
                            "--socket-path=/tmp/receptor/receptor.sock",
                            f"--listen-port={node.listen_port}",
                        ]
                    )
                    op = subprocess.Popen(" ".join(starter), shell=True)
                    procs.append(op)
                f.write(f"{' '.join(starter)}\n")
                sleep(2)
            else:
                peer_string = " ".join(
                    [
                        f"--peer=localhost:{topology[pnode].listen_port}"
                        for pnode in node.connections
                    ]
                )
                if not DEBUG:
                    starter = start[:]
                    starter.extend(
                        [
                            "-d",
                            "/tmp/receptor",
                            "--node-id",
                            node.name,
                            "node",
                            f"--listen-port={node.listen_port}",
                            peer_string,
                        ]
                    )
                    op = subprocess.Popen(" ".join(starter), shell=True)
                    procs.append(op)
                f.write(f"{' '.join(starter)}\n")
                sleep(0.1)

    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        for proc in procs:
            proc.kill()


def load_topology(filename):
    data = yaml.safe_load(filename)
    topology = {}
    for node, definition in data["nodes"].items():
        topology[node] = Node(
            definition["name"],
            definition["controller"],
            definition.get("listen_port", None) or random_port(),
            definition["connections"],
        )
    return topology


@click.group(help="Helper commands for application")
def main():
    pass


@main.command("random")
@click.option("--debug", is_flag=True, default=False)
@click.option("--controller-port", help="Chooses Controller port", default=8888)
@click.option("--node-count", help="Choose number of nodes", default=10)
@click.option("--max-conn-count", help="Choose max number of connections per node", default=2)
@click.option("--profile", is_flag=True, default=False)
def randomize(controller_port, node_count, max_conn_count, debug):
    if debug:
        global DEBUG
        DEBUG = True

    def peer_function(nodes, cur_node):
        nconns = defaultdict(int)
        print(nodes)
        for k, node in nodes.items():
            for conn in node.connections:
                nconns[conn] += 1
        available_nodes = list(filter(lambda o: nconns[o] < max_conn_count, nodes))
        print("------")
        print(nconns)
        print(available_nodes)
        print(cur_node.name)
        print(random.choices(available_nodes, k=int(random.random() * max_conn_count)))
        print("----")
        if cur_node.name not in available_nodes:
            return []
        else:
            return random.choices(available_nodes, k=int(random.random() * max_conn_count))

    node_topology = generate_random_mesh(controller_port, node_count, peer_function)
    print(node_topology)
    do_it(node_topology)


@main.command("flat")
@click.option("--debug", is_flag=True, default=False)
@click.option("--controller-port", help="Chooses Controller port", default=8888)
@click.option("--node-count", help="Choose number of nodes", default=10)
@click.option("--profile", is_flag=True, default=False)
def flat(controller_port, node_count, debug):
    if debug:
        global DEBUG
        DEBUG = True

    def peer_function(nodes, cur_node):
        return ["controller"]

    node_topology = generate_random_mesh(controller_port, node_count, peer_function)
    print(node_topology)
    do_it(node_topology)


@main.command("file")
@click.option("--debug", is_flag=True, default=False)
@click.option("--profile", is_flag=True, default=False)
@click.argument("filename", type=click.File("r"))
def file(filename, debug, profile):
    topology = load_topology(filename)
    do_it(topology, profile=profile)


@main.command("ping")
@click.option("--validate", default=None)
@click.option("--count", default=10)
@click.argument("filename", type=click.File("r"))
def ping(filename, count, validate):
    topology = load_topology(filename)
    results = {}
    for name, node in topology.items():
        starter = [
            "time",
            "receptor",
            "ping",
            "--socket-path",
            "/tmp/receptor/receptor.sock",
            node.name,
            "--count",
            str(count),
        ]
        start = time.time()
        op = subprocess.Popen(" ".join(starter), shell=True, stdout=subprocess.PIPE)
        op.wait()
        duration = time.time() - start
        cmd_output = op.stdout.readlines()
        print(cmd_output)
        if b"Failed" in cmd_output[0]:
            results[node.name] = "Failed"
        else:
            results[node.name] = duration / count
    with open("results.yaml", "w") as f:
        yaml.dump(results, f)
    if validate:
        valid = True
        for node in results:
            if topology[node].controller:
                continue
            print(f"Asserting node {node} was under {validate} threshold")
            print(f"  {results[node]}")
            if results[node] == "Failed" or float(results[node]) > float(validate):
                valid = False
                print("  FAILED!")
            else:
                print("  PASSED!")
        if not valid:
            sys.exit(127)


if __name__ == "__main__":
    main()
