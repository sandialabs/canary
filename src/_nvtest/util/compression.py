import base64
import io
import json
import os
import zlib
from typing import Optional


def serialize(obj: object) -> str:
    string = str(json.dumps(obj))
    return compress64(string)


def deserialize(raw: str) -> object:
    string = expand64(raw)
    return json.loads(string)


def compress64(string: str) -> str:
    compressed = zlib.compress(string.encode("utf-8"))
    return base64.b64encode(compressed).decode("utf-8")


def expand64(raw: str) -> str:
    bytes_str = base64.b64decode(raw.encode("utf-8"))
    hex_str = bytes_str.hex()
    s = zlib.decompress(bytes.fromhex(hex_str))
    return s.decode("utf-8")


def compress_file(file, kb_to_keep: Optional[int] = None) -> str:
    if file is None:
        txt = "No file found!"
    elif not os.path.exists(file):
        txt = f"File {file!r} not found!"
    else:
        txt = io.open(file, errors="ignore").read()
    if isinstance(kb_to_keep, int):
        kb = 1024
        bytes_to_keep = kb_to_keep * kb
        if len(txt) > bytes_to_keep:
            rule = "=" * 100 + "\n"
            fmt = "\n\n{0}{0}Output truncated to {1} kb\n{0}{0}\n"
            txt = txt[:kb] + fmt.format(rule, kb_to_keep) + txt[-(bytes_to_keep - kb) :]
    return compress64(txt)
