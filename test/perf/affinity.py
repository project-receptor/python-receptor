import random
from collections import defaultdict
import subprocess
import attr
import atexit
from utils import random_port
import uuid
import yaml

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
            st.extend(["-d", self.data_path, "--node-id", self.name, "node"])
            st.extend([f"--listen-port={self.listen_port}", peer_string])

        if self.stats_enable:
            st.extend(["--stats-enable", f"--stats-port={self.stats_port}"])

        return st

    def start(self):
        op = subprocess.Popen(" ".join(self._construct_run_command()), shell=True)
        procs[self.uuid] = op

    def stop(self):
        print(f"killing {self.name}({self.uuid})")
        procs[self.uuid].kill()


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
    def generate_mesh(
        controller_port, node_count, conn_method, profile=False, socket_path=None
    ):
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
            f.write("graph {")
            for node, node_data in self.nodes.items():
                for conn in node_data.connections:
                    f.write(f"{node} -- {conn}; ")
            f.write("}")

    def start(self):
        self.dump_yaml()
        self.dump_dot()

        for k, node in self.nodes.items():
            node.start()

    def stop(self):
        for k, node in self.nodes.items():
            node.stop()
        print("all killed")

    @staticmethod
    def load_topology_from_file(filename):
        data = yaml.safe_load(filename)
        topology = Topology()
        for node_name, definition in data["nodes"].items():
            node = Node.create_from_config(definition)
            topology.add_node(node)

        return topology

    def find_controller(self):
        return list(filter(lambda o: o.controller, self.nodes.values()))
