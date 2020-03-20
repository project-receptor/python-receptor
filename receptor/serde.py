import datetime
import json
from functools import partial, singledispatch

decoders = {}


def decoder(typename):
    def _inner(func):
        decoders[typename] = func
        return func

    return _inner


def decode(o):
    try:
        return decoders[o["_type"]](o["value"])
    except Exception:
        return o


@singledispatch
def encode(o):
    return json.JSONEncoder().default(o)


def wrapped_encode(o):
    try:
        return encode(o)
    except TypeError:
        return str(o)


@encode.register(datetime.datetime)
def encode_date(obj):
    return {"_type": "datetime.datetime", "value": obj.timestamp()}


@decoder("datetime.datetime")
def decode_date(value):
    return datetime.datetime.fromtimestamp(value)


load = partial(json.load, object_hook=decode)
loads = partial(json.loads, object_hook=decode)
dump = partial(json.dump, default=encode)
dumps = partial(json.dumps, default=encode)

force_dumps = partial(json.dumps, default=wrapped_encode)
