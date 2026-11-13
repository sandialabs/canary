# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Helpers for normalising filesystem scanpath inputs.

These helpers convert exact paths and globbed filesystem patterns into the
``{file_root: [relative paths]}`` structure used throughout Canary.
"""

from __future__ import annotations

import glob
import os


def is_glob_pattern(path: str) -> bool:
    """Return ``True`` when *path* contains Python glob metacharacters."""
    return glob.has_magic(path)


def merge_scanpaths(dst: dict[str, list[str]], src: dict[str, list[str]]) -> None:
    """Merge *src* into *dst* using Canary's root/subpath semantics."""
    for root, paths in src.items():
        existing = dst.get(root)
        if existing == [] or paths == []:
            dst[root] = []
            continue
        merged = set(existing or [])
        merged.update(paths)
        dst[root] = sorted(merged, key=lambda p: (len(p.split(os.sep)), p))


def scanpath_from_item(item: str) -> dict[str, list[str]] | None:
    """Return scanpaths for *item*, or ``None`` if it is not a filesystem path."""
    explicit_root = _explicit_root_prefix(item)
    if explicit_root is not None:
        root, path = explicit_root
        return _scanpath_from_root_path(root, path, display=item)

    abspath = os.path.abspath(item)

    if os.path.isdir(abspath):
        return {abspath: []}

    if os.path.isfile(abspath):
        root, name = os.path.split(abspath)
        return {root: [name]}

    if is_glob_pattern(item):
        if os.pathsep in item:
            raise ValueError(f"{item}: ':' is only allowed before the first globbed component")
        return _scanpath_from_glob(item)

    return None


def scanpaths_from_root_paths(root: str, paths: list[str]) -> dict[str, list[str]]:
    """Return scanpaths for *paths* interpreted relative to *root*."""
    root = os.path.abspath(root)
    merged: dict[str, list[str]] = {}
    if not paths:
        return {root: []}
    for path in paths:
        merge_scanpaths(merged, _scanpath_from_root_path(root, path))
    return merged


def _scanpath_from_root_path(
    root: str, path: str, *, display: str | None = None
) -> dict[str, list[str]]:
    root = os.path.abspath(root)
    candidate = os.path.join(root, path)
    if os.pathsep in path:
        raise ValueError(
            f"{display or path}: ':' is only allowed before the first globbed component"
        )
    if is_glob_pattern(path):
        return _scanpath_from_glob(candidate, file_root=root, display=display or path)
    if os.path.exists(candidate):
        return {root: [os.path.normpath(path)]}
    raise ValueError(f"{display or path}: no such file or directory")


def _scanpath_from_glob(
    pattern: str, *, file_root: str | None = None, display: str | None = None
) -> dict[str, list[str]]:
    abs_pattern = os.path.abspath(pattern)
    root = os.path.abspath(file_root) if file_root is not None else _literal_file_root(abs_pattern)
    matches = sorted({os.path.abspath(match) for match in glob.glob(abs_pattern, recursive=True)})
    if not matches:
        raise ValueError(f"{display or pattern}: no paths matched pattern")

    relpaths: list[str] = []
    for match in matches:
        relpath = os.path.relpath(match, root)
        if relpath == ".":
            return {root: []}
        relpaths.append(os.path.normpath(relpath))
    return {root: sorted(relpaths, key=lambda p: (len(p.split(os.sep)), p))}


def _literal_file_root(pattern: str) -> str:
    parts = os.path.abspath(pattern).split(os.sep)
    literal_parts: list[str] = []
    for part in parts:
        if literal_parts or part:
            if glob.has_magic(part):
                break
        literal_parts.append(part)

    if not literal_parts:
        return os.path.abspath(os.curdir)
    root = os.sep.join(literal_parts)
    return root or os.sep


def _explicit_root_prefix(item: str) -> tuple[str, str] | None:
    parts = item.split(os.pathsep)
    if len(parts) < 2:
        return None
    prefix = parts[0]
    for i in range(1, len(parts)):
        candidate = os.pathsep.join(parts[:i])
        if os.path.isdir(candidate):
            suffix = os.pathsep.join(parts[i:])
            return candidate, suffix
        prefix = os.pathsep.join(parts[: i + 1])
        if glob.has_magic(prefix):
            raise ValueError(f"{item}: ':' is only allowed before the first globbed component")
    return None


class TestPathsFileError(ValueError):
    """A ``testpaths`` file (``-f FILE``) is unreadable, malformed, or lists missing paths."""

    __test__ = False  # not a pytest test class, despite the name


def read_testpaths_file(file: str) -> dict[str, list[str]]:
    """Read a JSON or YAML ``testpaths`` file and return ``{abs_root: [rel_paths]}``.

    Each ``root`` is resolved relative to the file's directory, and each entry
    in ``paths`` relative to its root.  A missing, ``null``, or empty ``paths``
    scans the whole root.  Entries may be files, directories, or
    glob patterns.  Every root and path is checked; all problems are reported
    together so a stale list can be fixed in one pass.

    Raises:
        TestPathsFileError: If the file cannot be read or parsed, does not match
            the schema (see ``canary help --pathfile``), or names a root or path
            that does not exist.
    """
    from schema import SchemaError

    from .config.schemas import testpaths_schema

    try:
        with open(file, "r") as fh:
            text = fh.read()
    except OSError as e:
        raise TestPathsFileError(f"{file}: cannot read testpaths file: {e.strerror}") from e

    try:
        if file.endswith(".json"):
            import json

            data = json.loads(text)
        else:
            import yaml

            data = yaml.safe_load(text)
    except ValueError as e:  # json.JSONDecodeError is a ValueError
        raise TestPathsFileError(f"{file}: invalid JSON: {e}") from e
    except Exception as e:  # yaml.YAMLError
        raise TestPathsFileError(f"{file}: invalid YAML: {e}") from e

    try:
        testpaths_schema.validate(data)
    except SchemaError as e:
        raise TestPathsFileError(
            f"{file}: does not match the testpaths schema ({e}); see 'canary help --pathfile'"
        ) from e

    file_dir = os.path.dirname(os.path.abspath(file))
    paths: dict[str, list[str]] = {}
    problems: list[str] = []
    for entry in data["testpaths"]:
        root = os.path.normpath(os.path.join(file_dir, entry["root"]))
        if not os.path.isdir(root):
            what = "is not a directory" if os.path.exists(root) else "does not exist"
            problems.append(f"root {entry['root']!r} {what} ({root})")
            continue
        entry_paths = entry.get("paths") or []
        if not entry_paths:
            merge_scanpaths(paths, {root: []})
            continue
        for path in entry_paths:
            try:
                merge_scanpaths(paths, _scanpath_from_root_path(root, path))
            except ValueError as e:
                problems.append(f"{os.path.join(entry['root'], path)}: {_short_reason(e, path)}")
    if problems:
        listing = "\n".join(f"  - {problem}" for problem in problems)
        noun = "problem" if len(problems) == 1 else "problems"
        raise TestPathsFileError(f"{file}: {len(problems)} {noun} in testpaths file:\n{listing}")
    return paths


def _short_reason(error: ValueError, path: str) -> str:
    """Strip the leading ``path: `` that the scanpath helpers prefix onto messages."""
    message = str(error)
    prefix = f"{path}: "
    return message[len(prefix) :] if message.startswith(prefix) else message
