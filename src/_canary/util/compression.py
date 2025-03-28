# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import base64
import io
import json
import os
import zlib


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


def compress_str(text: str, kb_to_keep: int | None = None) -> str:
    if kb_to_keep is not None:
        kb = 1024
        bytes_to_keep = kb_to_keep * kb
        if len(text) > bytes_to_keep:
            rule = "=" * 100 + "\n"
            fmt = "\n\n{0}{0}Output truncated to {1} kb\n{0}{0}\n"
            text = text[:kb] + fmt.format(rule, kb_to_keep) + text[-(bytes_to_keep - kb) :]
    return compress64(text)


def compress_file(file: str, kb_to_keep: int | None = None) -> str:
    if not os.path.exists(file):
        txt = f"File {file!r} not found!"
    else:
        txt = io.open(file, errors="ignore").read()
    return compress_str(txt, kb_to_keep=kb_to_keep)
