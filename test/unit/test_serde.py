import datetime

from receptor.serde import dumps, loads


def test_date_serde():

    o = {"now": datetime.datetime.utcnow()}

    serialized = dumps(o)
    deserialized = loads(serialized)

    assert deserialized == o
