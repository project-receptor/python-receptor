class Connection:
    def __init__(self, id_, meta, protocol_obj):
        self.id_ = id_
        self.meta = meta
        self.protocol_obj = protocol_obj

    def __str__(self):
        return f"<Connection {self.id_} {self.protocol_obj}>"
