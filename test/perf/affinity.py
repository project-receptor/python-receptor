import atexit
import os
import random
import subprocess
import time
import uuid
from collections import defaultdict
from test.perf.utils import random_port
from test.perf.utils import read_and_parse_dot
import signal

import attr
import yaml
from pyparsing import ParseException
from wait_for import wait_for

procs = {}


def shut_all_procs():
    for proc in procs.values():
        proc.kill()


atexit.register(shut_all_procs)


@attr.s
class Node:
    name = attr.ib()
    controller = attr.ib(default=False)
    listen_port = attr.ib(factory=random_port)
    connections = attr.ib(factory=list)
    stats_enable = attr.ib(default=False)
    stats_port = attr.ib(default=None)
    profile = attr.ib(default=False)
    socket_path = attr.ib(default=None)
    data_path = attr.ib(default=None)
    topology = attr.ib(init=False, default=None)
    uuid = attr.ib(init=False, factory=uuid.uuid4)

    def __attrs_post_init__(self):
        if not self.socket_path:
            self.socket_path = f"/tmp/receptor/{str(self.uuid)}/receptor.sock"
        if not self.data_path:
            self.data_path = f"/tmp/receptor/{str(self.uuid)}"

    @staticmethod
    def create_from_config(config):
        return Node(
            name=config["name"],
            controller=config.get("controller", False),
            listen_port=config.get("listen_port", None) or random_port(),
            connections=config.get("connections", []) or [],
            stats_enable=config.get("stats_enable", False),
            stats_port=config.get("stats_port", None) or random_port(),
            profile=config.get("profile", False),
            socket_path=config.get("socket_path", None),
            data_path=config.get("data_path", None),
        )

    def _construct_run_command(self):
        if self.profile:
            st = ["python", "-m", "cProfile", "-o", f"{self.name}.prof", "-m", "receptor.__main__"]
        else:
            st = ["receptor"]

        if self.controller:
            st.extend(["--debug", "-d", self.data_path, "--node-id", self.name, "controller"])
            st.extend([f"--socket-path={self.socket_path}"])
            st.extend([f"--listen-port={self.listen_port}"])
        else:
            peer_string = " ".join(
                [
                    f"--peer=localhost:{self.topology.nodes[pnode].listen_port}"
                    for pnode in self.connections
                ]
            )
            st.extend(["--debug", "-d", self.data_path, "--node-id", self.name, "node"])
            st.extend([f"--listen-port={self.listen_port}", peer_string])

        if self.stats_enable:
            st.extend(["--stats-enable", f"--stats-port={self.stats_port}"])

        return st

    def start(self):
        try:
            os.remove(f"graph_{self.name}.dot")
            os.sync()
        except FileNotFoundError:
            print(f"DIND'T FIND IT graph_{self.name}.dot")
        print(f"{time.time()} starting {self.name}({self.uuid})")
        op = subprocess.Popen(" ".join(self._construct_run_command()), shell=True, preexec_fn=os.setsid)
        procs[self.uuid] = op

    def stop(self):
        print(f"{time.time()} killing {self.name}({self.uuid})")
        try:
            os.killpg(os.getpgid(procs[self.uuid].pid), signal.SIGTERM)
        except ProcessLookupError:
            print("Couldn't kill the process {procs[self.uuid].pid}")
        procs[self.uuid].wait()
        print(f"Service was kill {procs[self.uuid].returncode}")

    def get_debug_dot(self):
        try:
            with open(f"graph_{self.name}.dot") as f:
                dot_data = f.read()
            #print(f"FILE FOUND: graph_{self.name}.dot")
            return dot_data
        except FileNotFoundError:
            #print(f"FILE NOT FOUND: graph_{self.name}.dot")
            return ""

    def validate_routes(self):
        dot1 = self.get_debug_dot()
        dot2 = self.topology.generate_dot()
        if dot1 and dot2:
            return self.topology.compare_dot(dot1, dot2)
        else:
            return False

    def ping(self, count):
        socket_path = self.topology.find_controller()[0].socket_path

        if self.controller:
            # TODO Remove this once a controller is pingable
            return True

        starter = [
            "time",
            "receptor",
            "ping",
            "--socket-path",
            socket_path,
            self.name,
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
            return "Failed"
        else:
            return duration / count


@attr.s
class Topology:
    nodes = attr.ib(init=False, factory=dict)

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
    def generate_mesh(controller_port, node_count, conn_method, profile=False, socket_path=None):
        topology = Topology()
        topology.add_node(
            Node(
                name="controller",
                controller=True,
                listen_port=controller_port,
                profile=profile,
                socket_path=socket_path,
            )
        )

        for i in range(node_count):
            topology.add_node(
                Node(name=f"node{i}", controller=False, listen_port=random_port(), profile=profile)
            )

        for k, node in topology.nodes.items():
            if node.controller:
                continue
            else:
                node.connections.extend(conn_method(topology, node))
        return topology

    @staticmethod
    def generate_random_mesh(controller_port, node_count, max_conn_count, profile, socket_path):
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
            controller_port, node_count, peer_function, profile, socket_path
        )
        return topology

    @staticmethod
    def generate_flat_mesh(controller_port, node_count, profile, socket_path):
        def peer_function(*args):
            return ["controller"]

        topology = Topology.generate_random_mesh(
            controller_port, node_count, peer_function, profile, socket_path
        )
        return topology

    def dump_yaml(self, filename=".last-topology.yaml"):
        with open(filename, "w") as f:
            data = {"nodes": {}}
            for node, node_data in self.nodes.items():
                data["nodes"][node] = {
                    "name": node_data.name,
                    "listen_port": node_data.listen_port if node_data.controller else None,
                    "controller": node_data.controller,
                    "connections": node_data.connections,
                    "stats_enable": node_data.stats_enable,
                    "stats_port": node_data.stats_port,
                }
                if node_data.socket_path:
                    data["nodes"][node]["socket_path"] = node_data.socket_path
                if node_data.data_path:
                    data["nodes"][node]["data_path"] = node_data.data_path

            yaml.dump(data, f)

    def dump_dot(self, filename=".last-topology-graph.dot"):
        with open(filename, "w") as f:
            f.write(self.generate_dot())

    def generate_dot(self):
        dot_data = "graph {"
        for node, node_data in self.nodes.items():
            for conn in node_data.connections:
                dot_data += f"{node} -- {conn}; "
        dot_data += "}"
        return dot_data

    def start(self, wait=True):
        self.dump_yaml()
        self.dump_dot()

        for k, node in self.nodes.items():
            node.start()

        if wait:
            wait_for(self.validate_all_node_routes, delay=6, num_sec=30)
            #for name, node in self.nodes.items():
            #    wait_for(lambda: node.validate_routes)

    def stop(self):
        for k, node in self.nodes.items():
            node.stop()
        print("all killed")

    @staticmethod
    def load_topology_from_file(filename):
        with open(filename) as f:
            data = yaml.safe_load(f)

        topology = Topology()
        for node_name, definition in data["nodes"].items():
            node = Node.create_from_config(definition)
            topology.add_node(node)

        return topology

    def find_controller(self):
        return list(filter(lambda o: o.controller, self.nodes.values()))

    def ping(self, count=10, socket_path=None):
        results = {}
        for _, node in self.nodes.items():
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
    def compare_dot(dot1, dot2):
        try:
            ds1 = read_and_parse_dot(dot1)
            ds2 = read_and_parse_dot(dot2)
            if ds1 != ds2:
                print(f"MATCH FAIL")
                print(ds1)
                print(ds2)
                return False
            return True
        except ParseException:
            return False

    def validate_all_node_routes(self):
        return all(node.validate_routes() for _, node in self.nodes.items())
