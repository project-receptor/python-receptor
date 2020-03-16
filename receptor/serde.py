import datetime
import json
from functools import partial


def encode_date(obj):
    if isinstance(obj, datetime.datetime):
        return {"_type": "datetime.datetime", "value": obj.timestamp()}
    raise TypeError


def decode_date(o):
    type_ = o.get("_type")
    if type_ != "datetime.datetime":
        return o
    return datetime.datetime.fromtimestamp(o["value"])


load = partial(json.load, object_hook=decode_date)
loads = partial(json.loads, object_hook=decode_date)
dump = partial(json.dump, default=encode_date)
dumps = partial(json.dumps, default=encode_date)
