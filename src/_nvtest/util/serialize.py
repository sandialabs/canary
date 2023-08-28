import base64
import pickle
import zlib
from typing import Any


def serialize(obj: Any) -> Any:
    b = pickle.dumps(obj, protocol=0)
    return compress64(b)


def deserialize(raw: Any) -> Any:
    string = expand64(raw)
    return pickle.loads(string)


def compress64(string: Any) -> Any:
    compressed = zlib.compress(string)
    return base64.b64encode(compressed).decode("utf-8")


def expand64(raw: Any) -> Any:
    bytes_str = base64.b64decode(raw.encode("utf-8"))
    hex_str = bytes_str.hex()
    return zlib.decompress(bytes.fromhex(hex_str))
