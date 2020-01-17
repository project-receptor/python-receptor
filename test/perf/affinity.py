import atexit
import json
import os
import random
import signal
import subprocess
import time
import uuid
from collections import defaultdict
from test.perf import debugger
from test.perf import ping
from test.perf.utils import Conn
from test.perf.utils import net_check
from test.perf.utils import random_port
from test.perf.utils import read_and_parse_metrics
from urllib.parse import quote
from urllib.parse import urlparse

import attr
import requests
import yaml
from prometheus_client.parser import text_string_to_metric_families
from wait_for import wait_for

STANDARD = 0
DIAG = 1

procs = {}


def shut_all_procs():
    for proc in procs.values():
        proc.kill()


atexit.register(shut_all_procs)


@attr.s
class Node:
    name = attr.ib()
    controller = attr.ib(default=False)
    listen = attr.ib(default=None)
    connections = attr.ib(factory=list)
    stats_enable = attr.ib(default=False)
    stats_port = attr.ib(default=None)
    profile = attr.ib(default=False)
    data_path = attr.ib(default=None)
    topology = attr.ib(init=False, default=None)
    uuid = attr.ib(init=False, factory=uuid.uuid4)
    active = attr.ib(init=False)

    node_type = STANDARD

    def __attrs_post_init__(self):
        if not self.data_path:
            self.data_path = f"/tmp/receptor/{str(self.uuid)}"
        if not self.listen:
            self.listen = f"receptor://0.0.0.0:{random_port()}"

    @staticmethod
    def create_from_config(config):
        return Node(
            name=config["name"],
            controller=config.get("controller", False),
            listen=config.get("listen", f"receptor://0.0.0.0:{random_port()}"),
            connections=config.get("connections", []) or [],
            stats_enable=config.get("stats_enable", False),
            stats_port=config.get("stats_port", None) or random_port(),
            profile=config.get("profile", False),
            data_path=config.get("data_path", None),
        )

    def _construct_run_command(self):
        if self.profile:
            st = ["python", "-m", "cProfile", "-o", f"{self.name}.prof", "-m", "receptor.__main__"]
        else:
            st = ["receptor"]

        if self.controller:
            st.extend(["-d", self.data_path, "--node-id", self.name, "controller"])
            st.extend([f"--listen={self.listen}"])
        else:
            peer_string = " ".join(
                [f"--peer={self.topology.nodes[pnode].listen}" for pnode in self.connections]
            )
            st.extend(["-d", self.data_path, "--node-id", self.name, "node"])
            st.extend([f"--listen={self.listen}", peer_string])

        if self.stats_enable:
            st.extend(["--stats-enable", f"--stats-port={self.stats_port}"])

        return st

    def start(self, wait_for_ports=True):
        print(f"{time.time()} starting {self.name}({self.uuid})")
        op = subprocess.Popen(
            " ".join(self._construct_run_command()), shell=True, preexec_fn=os.setsid
        )
        procs[self.uuid] = op

        if wait_for_ports:
            self.wait_for_ports()
        self.active = True

    def wait_for_ports(self):
        print("waiting for nodes ports " + self.name)
        print(self.port, self.hostname)
        wait_for(net_check, func_args=[self.port, self.hostname, True], num_sec=10)
        if self.stats_enable:
            wait_for(net_check, func_args=[self.stats_port, self.hostname, True], num_sec=10)

    def stop(self):
        print(f"{time.time()} killing {self.name}({self.uuid})")
        try:
            os.killpg(os.getpgid(procs[self.uuid].pid), signal.SIGKILL)  # TODO NICE FOR DEBUGGER
        except ProcessLookupError:
            print(f"Couldn't kill the process {procs[self.uuid].pid}")
        procs[self.uuid].wait()
        print(f"Service was kill {procs[self.uuid].returncode}")
        self.active = False

    @property
    def hostname(self):
        return urlparse(self.listen).hostname

    @property
    def port(self):
        return urlparse(self.listen).port

    def get_metrics(self):
        stats = requests.get(f"http://{self.hostname}:{self.stats_port}/metrics")
        metrics = {metric.name: metric for metric in text_string_to_metric_families(stats.text)}
        return metrics

    def get_routes(self):
        routes = self.get_metrics()["routing_table_info"].samples[0].labels["edges"]
        if routes == "()":
            return set()
        else:
            return read_and_parse_metrics(routes)

    def validate_routes(self):
        if not self.active:
            raise Exception("Can't get routes from a stopped node")
        print(f"****====TRYING COMPARE {self.name}")
        node_routes = self.get_routes()
        control_routes = self.topology.generate_routes()
        if node_routes and control_routes:
            return self.topology.compare_routes(node_routes, control_routes)
        else:
            return False

    def ping(self, count, peer=None, node_ping_name="ping_node"):

        if self.topology.diag_node:
            return self.topology.diag_node.ping(count=count, recipient=self.name)

        if not peer:
            peer = self.topology.find_controller()[0]

        if node_ping_name not in self.topology.nodes:
            self.topology.add_node(DiagNode(name=node_ping_name))

        if peer.name not in self.topology.nodes[node_ping_name].connections:
            self.topology.nodes[node_ping_name].connections.append(peer.name)

        peer_address = self.topology.nodes[peer.name].listen

        starter = [
            "time",
            "python",
            ping.__file__,
            "--data-path",
            self.data_path,
            "--node-id",
            node_ping_name,
            "--peer",
            peer_address,
            "--id",
            self.name,
            "--count",
            str(count),
        ]
        print(starter)
        start = time.time()
        op = subprocess.Popen(
            " ".join(starter), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        op.wait()
        duration = time.time() - start
        cmd_output = op.stdout.readlines()
        print(op.stderr.read())
        print(cmd_output)
        if b"Failed" in cmd_output[0]:
            return "Failed"
        else:
            return duration / count


@attr.s
class DiagNode(Node):
    api_address = attr.ib(default="0.0.0.0")
    api_port = attr.ib(default=8080)
    node_type = DIAG

    def _construct_run_command(self):
        starter = [
            "python",
            debugger.__file__,
            "--listen",
            self.listen,
            "--data-path",
            self.data_path,
            "--api-address",
            self.api_address,
            "--api-port",
            str(self.api_port),
        ]
        print(starter)
        return starter

    def wait_for_ports(self):
        print(f"waiting for {self.api_port}, {self.api_address}")
        wait_for(net_check, func_args=[self.api_port, self.api_address, True])
        super().wait_for_ports()

    def validate_routes(self):
        print(f"****====TRYING COMPARE {self.name}")
        node_routes = self.get_routes()
        control_routes = self.topology.generate_routes()
        if node_routes and control_routes:
            return self.topology.compare_routes(node_routes, control_routes)
        else:
            return False

    def get_routes(self):
        route_data = json.loads(
            requests.get(f"http://{self.api_address}:{self.api_port}/connections").text
        )
        routes = set()
        for route in route_data:
            routes.add(Conn(route[0], route[1], route[2]))
        return routes

    def ping(self, count=5, recipient="controller"):
        output = requests.get(
            f"http://{self.api_address}:{self.api_port}/ping?count={count}&recipient={recipient}"
        ).text

        if "Failed" in output:
            return "Failed"
        else:
            times = json.loads(output)
            return sum(times) / len(times)

    def add_peer(self, peer):
        coded_peer = quote(peer.listen)
        requests.get(f"http://{self.api_address}:{self.api_port}/add_peer?peer={coded_peer}")

    def create_from_config(config):
        raise NotImplementedError


@attr.s
class Topology:
    use_diag_node = attr.ib(default=False)
    nodes = attr.ib(init=False, factory=dict)
    diag_node = attr.ib(init=False, default=None)

    def __attrs_post_init__(self):
        if self.use_diag_node:
            self.diag_node = DiagNode(
                name="diag_node", listen=f"receptor://127.0.0.1:{random_port()}"
            )
            self.add_node(self.diag_node)

    def add_node(self, node):
        if node.name not in self.nodes:
            self.nodes[node.name] = node
            node.topology = self
        else:
            raise Exception("Topology already has a node by the same name")

    def remove_node(self, node_or_name):
        if isinstance(node_or_name, Node):
            node_name = node_or_name.name
        else:
            node_name = node_or_name
        if node_name not in self.nodes:
            raise Exception("Topology has no node by that name")
        else:
            self.nodes[node_name].topology = None
            del self.nodes[node_name]

    @staticmethod
    def generate_mesh(controller_port, node_count, conn_method, profile=False):
        topology = Topology()
        topology.add_node(
            Node(
                name="controller",
                controller=True,
                listen=f"receptor://127.0.0.1:{controller_port}",
                profile=profile,
            )
        )

        for i in range(node_count):
            topology.add_node(
                Node(
                    name=f"node{i}",
                    controller=False,
                    listen=f"receptor://127.0.0.1:{random_port()}",
                    profile=profile,
                )
            )

        for k, node in topology.nodes.items():
            if node.controller:
                continue
            else:
                node.connections.extend(conn_method(topology, node))
        return topology

    @staticmethod
    def generate_random_mesh(controller_port, node_count, max_conn_count, profile):
        def peer_function(topology, cur_node):
            nconns = defaultdict(int)
            print(topology)
            for k, node in topology.nodes.items():
                for conn in node.connections:
                    nconns[conn] += 1
            available_nodes = list(filter(lambda o: nconns[o] < max_conn_count, topology.nodes))
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

        topology = Topology.generate_random_mesh(
            controller_port, node_count, peer_function, profile
        )
        return topology

    @staticmethod
    def generate_flat_mesh(controller_port, node_count, profile):
        def peer_function(*args):
            return ["controller"]

        topology = Topology.generate_random_mesh(
            controller_port, node_count, peer_function, profile
        )
        return topology

    def dump_yaml(self, filename=".last-topology.yaml"):
        with open(filename, "w") as f:
            data = {"nodes": {}}
            for node, node_data in self.nodes.items():
                data["nodes"][node] = {
                    "name": node_data.name,
                    "listen": node_data.listen if node_data.controller else None,
                    "controller": node_data.controller,
                    "connections": node_data.connections,
                    "stats_enable": node_data.stats_enable,
                    "stats_port": node_data.stats_port,
                }
                if node_data.data_path:
                    data["nodes"][node]["data_path"] = node_data.data_path

            yaml.dump(data, f)

    def generate_routes(self):
        routes = set()
        for node, node_data in self.nodes.items():
            for conn in node_data.connections:
                routes.add(Conn(node_data.name, conn, 1))
        return routes

    def generate_dot(self):
        dot_data = "graph {"
        for node, node_data in self.nodes.items():
            for conn in node_data.connections:
                dot_data += f"{node} -- {conn}; "
        dot_data += "}"
        return dot_data

    def start(self, wait=True):
        self.dump_yaml()

        for k, node in self.nodes.items():
            node.start(wait_for_ports=not wait)

        if wait:
            print("Waiting for nodes")
            for _, node in self.nodes.items():
                node.wait_for_ports()
            if self.use_diag_node:
                self.diag_node.add_peer(self.find_controller()[0])
                self.nodes[self.diag_node.name].connections.append(self.find_controller()[0].name)
            wait_for(self.validate_all_node_routes, delay=6, num_sec=30)
            # for name, node in self.nodes.items():
            #    wait_for(lambda: node.validate_routes)

    def stop(self):
        for k, node in self.nodes.items():
            node.stop()
        print("all killed")

    @staticmethod
    def load_topology_from_file(filename, use_diag_node=False):
        with open(filename) as f:
            data = yaml.safe_load(f)

        topology = Topology(use_diag_node=use_diag_node)
        for node_name, definition in data["nodes"].items():
            node = Node.create_from_config(definition)
            topology.add_node(node)

        return topology

    def find_controller(self):
        return list(filter(lambda o: o.controller, self.nodes.values()))

    def ping(self, count=10):
        results = {}

        # Need to grab the list of nodes prior to running as pinging adds a node
        nodes = list(self.nodes.keys())
        for node_name in nodes:
            node = self.nodes[node_name]
            results[node.name] = node.ping(count)
        return results

    @staticmethod
    def validate_ping_results(results, threshold=0.1):
        valid = True
        for node in results:
            print(f"Asserting node {node} was under {threshold} threshold")
            print(f"  {results[node]}")
            if results[node] == "Failed" or float(results[node]) > float(threshold):
                valid = False
        return valid

    @staticmethod
    def compare_routes(route1, route2):
        if route1 != route2:
            print(f"****====MATCH FAIL")
            print(route1)
            print(route2)
            return False
        else:
            print("****====MATCH")
            return True

    def validate_all_node_routes(self):
        return all(node.validate_routes() for node in self.nodes.values() if node.active)
