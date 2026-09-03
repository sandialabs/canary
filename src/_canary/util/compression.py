# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Compression and serialization helpers using zlib and base-64 encoding.

Key functions: ``compress64``/``expand64`` for raw string compression,
``serialize``/``deserialize`` for JSON-object round-trips, and
``compress_file``/``compress_str`` for optional size-capped file compression.
"""

import base64
import io
import os
import tarfile
import zlib
from typing import Any

from . import json_helper as json


def targz_compress(*files: str, path: str | None = None) -> str:
    """Create a gzip-compressed tar archive from ``files`` and return it as a base-64 string.

    Args:
        *files: Paths to the files to archive.
        path: Optional subdirectory prefix to prepend to each filename inside the archive.

    Returns:
        Base-64-encoded bytes of the resulting ``.tar.gz`` archive.
    """
    buffer = io.BytesIO()
    with tarfile.open(mode="w:gz", fileobj=buffer) as tar:
        for file in files:
            with open(file, "rb") as fh:
                data = fh.read()
            name = os.path.basename(file)
            info = tarfile.TarInfo(name=name if path is None else f"{path}/{name}")
            info.size = len(data)
            tar.addfile(info, fileobj=io.BytesIO(data))
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def serialize(obj: Any) -> str:
    """JSON-serialize ``obj`` and return a zlib/base-64 compressed string.

    Args:
        obj: A JSON-serializable Python object.

    Returns:
        Compressed, base-64-encoded representation of the JSON form of ``obj``.
    """
    string = str(json.dumps(obj, separators=(",", ":"), sort_keys=True))
    return compress64(string)


def deserialize(raw: str) -> Any:
    """Decompress a string produced by ``serialize`` and return the Python object.

    Args:
        raw: A base-64/zlib compressed JSON string.

    Returns:
        The original Python object.
    """
    string = expand64(raw)
    return json.loads(string)


def compress64(string: str) -> str:
    """Compress a UTF-8 string with zlib and encode the result as base-64.

    Args:
        string: Plain-text string to compress.

    Returns:
        Base-64-encoded compressed bytes as a string.
    """
    compressed = zlib.compress(string.encode("utf-8"), level=zlib.Z_BEST_COMPRESSION)
    return base64.b64encode(compressed).decode("utf-8")


def expand64(raw: str) -> str:
    """Decode a base-64 string and decompress the zlib payload.

    Args:
        raw: Base-64-encoded zlib-compressed string.

    Returns:
        The original plain-text string.
    """
    bytes_str = base64.b64decode(raw.encode("utf-8"))
    return zlib.decompress(bytes_str).decode("utf-8")


def compress_str(text: str, kb_to_keep: int | None = None) -> str:
    """Compress a string, optionally truncating it to ``kb_to_keep`` kilobytes first.

    When the string exceeds ``kb_to_keep`` KB it is truncated symmetrically
    (keeping the first 1 KB and the tail) and a notice is inserted in the
    middle before compression.

    Args:
        text: Input text to compress.
        kb_to_keep: Maximum size in kilobytes to retain before compressing.
            If ``None``, the full string is compressed.

    Returns:
        Compressed, base-64-encoded string.
    """
    if kb_to_keep is not None:
        kb = 1024
        bytes_to_keep = kb_to_keep * kb
        if len(text) > bytes_to_keep:
            rule = "=" * 100 + "\n"
            fmt = "\n\n{0}{0}Output truncated to {1} kb\n{0}{0}\n"
            text = text[:kb] + fmt.format(rule, kb_to_keep) + text[-(bytes_to_keep - kb) :]
    return compress64(text)


def compress_file(file: str, kb_to_keep: int | None = None) -> str:
    """Read a file and return its compressed representation.

    If the file does not exist a placeholder message is compressed instead.

    Args:
        file: Path to the file to compress.
        kb_to_keep: Optional size cap in kilobytes passed to ``compress_str``.

    Returns:
        Compressed, base-64-encoded file contents.
    """
    if not os.path.exists(file):
        txt = f"File {file!r} not found!"
    else:
        txt = io.open(file, errors="ignore").read()
    return compress_str(txt, kb_to_keep=kb_to_keep)
