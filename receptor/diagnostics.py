import asyncio
import inspect
import json
import logging
import os
import signal
import traceback as tb
import types
from collections import defaultdict, deque
from datetime import datetime
from functools import singledispatch

from prometheus_client import generate_latest

from . import fileio
from .logstash_formatter.logstash import LogstashFormatter

logger = logging.getLogger(__name__)

log_buffer = deque(maxlen=10)
fmt = LogstashFormatter()
trigger = asyncio.Event()

signal.signal(signal.SIGHUP, lambda n, h: trigger.set())


@singledispatch
def extract_module(o):
    return o.__module__


@extract_module.register(types.CoroutineType)
def extract_coro(coro):
    return inspect.getmodule(coro, coro.cr_code.co_filename).__name__


@extract_module.register(types.GeneratorType)
def extract_gen(gen):
    return inspect.getmodule(gen, gen.gi_code.co_filename).__name__


@singledispatch
def encode(o):
    return json.JSONEncoder().default(o)


@encode.register(set)
def encode_set(s):
    return list(s)


@encode.register(bytes)
def decode_bytes(b):
    return b.decode("utf-8")


@encode.register(types.FunctionType)
def encode_function_type(func):
    return f"{func.__module__}.{func.__qualname__}"


@encode.register(datetime)
def encode_datetime(o):
    return o.isoformat()


def structure_task(task):
    coro = task._coro
    try:
        mod = extract_module(coro)
    except Exception:
        mod = "<unknown>"

    out = {"state": task._state, "name": f"{mod}.{coro.__qualname__}", "stack": []}

    try:
        stack = tb.extract_stack(task.get_stack()[0])
        out["stack"] = [
            {"filename": fs.filename, "line": fs.line, "lineno": fs.lineno} for fs in stack
        ]
    except IndexError:
        pass

    return out


def tasks():
    d = defaultdict(list)
    for t in asyncio.Task.all_tasks():
        st = structure_task(t)
        state = st.pop("state")
        d[state].append(st)
    return [{"state": state, "items": tasks} for state, tasks in d.items()]


def format_connection(node_id, connection, capabilities):
    d = connection._diagnostics()
    d["node_id"] = node_id
    d["capabilities"] = capabilities
    return d


def format_router(router):
    edges = [
        {"left": edge[0], "right": edge[1], "cost": cost} for edge, cost in router._edges.items()
    ]

    neighbors = [
        {"node_id": node_id, "items": values} for node_id, values in router._neighbors.items()
    ]

    table = [
        {"destination_node_id": node_id, "next_hop": v[0], "cost": v[1]}
        for node_id, v in router.routing_table.items()
    ]

    return {"nodes": router._nodes, "edges": edges, "neighbors": neighbors, "table": table}


async def status(receptor_object):
    path = os.path.join(receptor_object.base_path, "diagnostics.json")
    doc = {}
    doc["config"] = receptor_object.config._parsed_args.__dict__
    doc["node_id"] = receptor_object.node_id
    while True:
        trigger.clear()
        doc["datetime"] = datetime.utcnow()
        doc["recent_errors"] = list(fmt._record_to_dict(r) for r in log_buffer)
        doc["connections"] = [
            format_connection(node_id, conn, receptor_object.node_capabilities[node_id])
            for node_id, connections in receptor_object.connections.items()
            for conn in connections
        ]
        doc["routes"] = format_router(receptor_object.router)
        doc["tasks"] = tasks()
        doc["metrics"] = generate_latest()
        try:
            await fileio.write(path, json.dumps(doc, default=encode), mode="w")
        except Exception:
            logger.exception("failed to dump diagnostic data")

        # run every 30 seconds, or when triggered
        try:
            await asyncio.wait_for(trigger.wait(), 30)
        except asyncio.TimeoutError:
            pass
