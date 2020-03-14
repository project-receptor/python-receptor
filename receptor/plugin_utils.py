BYTES_PAYLOAD = "bytes"
BUFFER_PAYLOAD = "buffer"
FILE_PAYLOAD = "file"


def plugin_export(payload_type):
    def decorator(func):
        func.receptor_export = True
        func.payload_type = payload_type
        return func

    return decorator
