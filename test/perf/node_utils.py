
import logging
import random

import subprocess
import sys
import time
from affinity import Topology, Node

from collections import defaultdict
from time import sleep


import click
import requests
import yaml
from prometheus_client.parser import text_string_to_metric_families
from pyparsing import alphanums
from pyparsing import Group
from pyparsing import OneOrMore
from pyparsing import ParseException
from pyparsing import Suppress
from pyparsing import Word


DEBUG = False

RECEPTOR_METRICS = (
    "active_work",
    "connected_peers",
    "incoming_messages",
    "route_events",
    "work_events",
)


class Conn:
    def __init__(self, a, b):
        self.a = a
        self.b = b

    def __eq__(self, other):
        if self.a == other.a and self.b == other.b or self.a == other.b and self.b == other.a:
            return True
        return False

    def __hash__(self):
        enps = [self.a, self.b]
        sorted_enps = sorted(enps)
        return hash(tuple(sorted_enps))

    def __repr__(self):
        return f"{self.a} -- {self.b}"


def do_loop(topology):
    topology.start()
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        topology.stop()


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

    topology = Topology.generate_random_mesh(
        controller_port, node_count, max_conn_count, profile, socket_path
    )
    print(topology)
    do_loop(topology)


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

    topology = Topology.generate_flat_mesh(
        controller_port, node_count, profile, socket_path
    )
    print(topology)
    do_loop(topology)


@main.command("file")
@click.option("--debug", is_flag=True, default=False)
@click.argument("filename", type=click.File("r"))
def file(filename, debug):
    topology = Topology.load_topology_from_file(filename)
    do_loop(topology)


@main.command("ping")
@click.option("--validate", default=None)
@click.option("--count", default=10)
@click.option("--socket-path", default=None)
@click.argument("filename", type=click.File("r"))
def ping(filename, count, validate, socket_path):
    topology = Topology.load_topology_from_file(filename)
    if not socket_path:
        socket_path = topology.find_controller()[0].socket_path

    results = {}
    for name, node in topology.nodes.items():
        starter = [
            "time",
            "receptor",
            "ping",
            "--socket-path",
            socket_path,
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
            if topology.nodes[node].controller:
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


def read_and_parse_dot(filename):
    group = Group(Word(alphanums) + Suppress("--") + Word(alphanums)) + Suppress(";")
    dot = Suppress("graph {") + OneOrMore(group) + Suppress("}")

    with open(filename) as f:
        raw_data = f.read()
    data = dot.parseString(raw_data).asList()
    return {Conn(c[0], c[1]) for c in data}


@main.command("dot-compare")
@click.option("--wait", default=None)
@click.argument("filename_one")
@click.argument("filename_two")
def dot_compare(filename_one, filename_two, wait):

    if wait:
        start = time.time()
        while True:
            try:
                assert read_and_parse_dot(filename_one) == read_and_parse_dot(filename_two)
                sys.stderr.write("Matched\n")
                sys.exit(0)
            except (AssertionError, ParseException, FileNotFoundError) as e:
                if time.time() < start + float(wait):
                    time.sleep(1)
                else:
                    sys.stderr.write("Failed match\n")
                    raise e
    else:
        try:
            assert read_and_parse_dot(filename_one) == read_and_parse_dot(filename_two)
            sys.stderr.write("Matched\n")
        except AssertionError:
            sys.stderr.write("Failed match\n")
            sys.exit(127)


@main.command("check-stats")
@click.option("--debug", is_flag=True, default=False)
@click.option("--profile", is_flag=True, default=False)
@click.argument("filename", type=click.File("r"))
def check_stats(filename, debug, profile):
    topology = Topology.load_topology_from_file(filename)
    failures = []

    for node in topology.nodes.values():
        if not node.stats_enable:
            continue
        stats = requests.get(f"http://localhost:{node.stats_port}/metrics")
        metrics = {
            metric.name: metric
            for metric in text_string_to_metric_families(stats.text)
            if metric.name in RECEPTOR_METRICS
        }
        expected_connected_peers = len(
            [n for n in topology.nodes.values() if node.name in n.connections]
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
