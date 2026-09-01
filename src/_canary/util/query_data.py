# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Utilities for Canary query/learn data.

This module contains generic helpers for:

- loading JSON resources from importable packages;
- evaluating Canary's lightweight query-path syntax;
- listing queryable object paths;
- identifying and exporting skill objects.

It intentionally does not depend on Canary configuration or the plugin manager.
"""

import json
import re
import sys
from importlib import resources
from pathlib import Path
from typing import Any
from typing import Iterator

import yaml


def load_query_data(package: str, filename: str) -> dict[str, Any] | None:
    """Load an optional JSON query-data resource from an importable package.

    Args:
        package: Importable package containing the JSON resource, e.g.
            ``"canary.data"`` or ``"canary_pyt.data"``.
        filename: JSON resource filename, e.g. ``"capabilities.json"`` or
            ``"skills.json"``.

    Returns:
        Parsed JSON object, or ``None`` if the package/resource does not exist.
    """
    try:
        path = resources.files(package).joinpath(filename)
    except ModuleNotFoundError:
        return None

    if not path.is_file():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def require_query_data(package: str, filename: str) -> dict[str, Any]:
    """Load a required JSON query-data resource from an importable package.

    Raises:
        FileNotFoundError: If the resource does not exist.
    """
    data = load_query_data(package, filename)

    if data is None:
        raise FileNotFoundError(f"{package}:{filename}")

    return data


# -------------------------------------------------------------------------
# Query path evaluator
# -------------------------------------------------------------------------


def query_json(data: Any, query: str) -> Any:
    """Evaluate a lightweight query path against JSON-like data.

    Supported syntax:

    - ``.`` for the selected root object;
    - ``foo.bar`` for nested object keys;
    - ``.foo.bar`` with optional leading dot;
    - ``array[0]`` for list indexes;
    - ``object["key.with.dots"]`` or ``object['key with spaces']`` for quoted keys.

    This is intentionally not jq.
    """
    query = query.strip()

    if not query or query == ".":
        return data

    if not query.startswith("."):
        query = "." + query

    current = data

    for token in parse_query(query):
        if isinstance(token, str):
            if not isinstance(current, dict):
                raise TypeError(
                    f"Cannot access key {token!r} on {type(current).__name__}; "
                    f"current value is not an object"
                )

            try:
                current = current[token]
            except KeyError:
                raise KeyError(format_missing_key_message(token, current)) from None

        elif isinstance(token, int):
            if not isinstance(current, list):
                raise TypeError(
                    f"Cannot access index {token} on {type(current).__name__}; "
                    f"current value is not an array"
                )

            try:
                current = current[token]
            except IndexError:
                n = len(current)
                raise IndexError(f"No such index: {token}. Array length is {n}.") from None

        else:
            raise TypeError(f"Unsupported query token: {token!r}")

    return current


def format_missing_key_message(key: str, current: dict[str, Any]) -> str:
    keys = sorted(str(k) for k in current.keys())

    if not keys:
        return f"No such key: {key!r}. Current object has no keys."

    preview = ", ".join(keys[:24])
    if len(keys) > 24:
        preview += ", ..."

    return f"No such key: {key!r}. Available keys: {preview}"


def parse_query(query: str) -> list[str | int]:
    tokens: list[str | int] = []
    i = 0

    while i < len(query):
        ch = query[i]

        if ch == ".":
            i += 1
            start = i

            while i < len(query) and query[i] not in ".[":
                i += 1

            if i > start:
                tokens.append(query[start:i])

            continue

        if ch == "[":
            token, i = parse_bracket(query, i)
            tokens.append(token)
            continue

        raise ValueError(f"Invalid query syntax at column {i + 1}: {query!r}")

    return tokens


def parse_bracket(query: str, i: int) -> tuple[str | int, int]:
    assert query[i] == "["
    j = i + 1

    if j >= len(query):
        raise ValueError(f"Unclosed bracket in query: {query!r}")

    if query[j] in ("'", '"'):
        quote = query[j]
        j += 1
        chars: list[str] = []

        while j < len(query):
            ch = query[j]

            if ch == "\\":
                if j + 1 >= len(query):
                    raise ValueError(f"Invalid escape in query: {query!r}")
                chars.append(query[j + 1])
                j += 2
                continue

            if ch == quote:
                j += 1
                if j >= len(query) or query[j] != "]":
                    raise ValueError(f"Expected closing bracket in query: {query!r}")
                return "".join(chars), j + 1

            chars.append(ch)
            j += 1

        raise ValueError(f"Unclosed quoted key in query: {query!r}")

    match = re.match(r"-?\d+", query[j:])
    if match:
        value = int(match.group(0))
        j += len(match.group(0))

        if j >= len(query) or query[j] != "]":
            raise ValueError(f"Expected closing bracket in query: {query!r}")

        return value, j + 1

    raise ValueError(f"Invalid bracket expression in query: {query!r}")


# -------------------------------------------------------------------------
# Query path formatting / listing
# -------------------------------------------------------------------------


def display_query_prefix(query: str) -> str:
    query = query.strip()

    if not query or query == ".":
        return ""

    return query[1:] if query.startswith(".") else query


def join_query_path(prefix: str, key: str) -> str:
    if not prefix:
        return key

    if is_simple_query_key(key):
        return f"{prefix}.{key}"

    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'{prefix}["{escaped}"]'


def is_simple_query_key(key: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key))


def list_json_object_paths(data: Any, query: str) -> list[str]:
    """List immediate child object paths below a JSON query point.

    Scalar children are intentionally omitted. This is intended as a discovery
    helper, not a complete JSON path enumerator.
    """
    selected = query_json(data, query)

    if not isinstance(selected, dict):
        return []

    prefix = display_query_prefix(query)

    rows: list[str] = []
    for key, value in sorted(selected.items(), key=lambda item: str(item[0])):
        if isinstance(value, dict):
            rows.append(join_query_path(prefix, str(key)))

    return rows


def print_query_paths(paths: list[str]) -> None:
    for path in paths:
        print(path)


def print_json(data: Any, *, terse: bool = False) -> None:
    if terse:
        json.dump(data, sys.stdout, separators=(",", ":"))
    else:
        json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


# -------------------------------------------------------------------------
# Skill helpers
# -------------------------------------------------------------------------


def is_skill_object(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get("name"), str)
        and isinstance(data.get("description"), str)
        and isinstance(data.get("body"), str)
    )


def iter_skill_objects(data: Any, *, prefix: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(query_path, skill_object)`` pairs below ``data``."""
    if is_skill_object(data):
        yield prefix, data
        return

    if not isinstance(data, dict):
        return

    for key, value in data.items():
        child_prefix = join_query_path(prefix, str(key))
        yield from iter_skill_objects(value, prefix=child_prefix)


def skill_to_markdown(skill: dict[str, Any]) -> str:
    """Convert a skill JSON object back to SKILL.md-style Markdown."""
    body = skill.get("body", "")

    if not isinstance(body, str):
        raise ValueError("Skill object must contain a string field: body")

    frontmatter = {key: value for key, value in skill.items() if key != "body"}

    name = frontmatter.get("name")
    description = frontmatter.get("description")

    if not isinstance(name, str) or not name:
        raise ValueError("Skill object must contain a non-empty string field: name")

    if not isinstance(description, str):
        raise ValueError("Skill object must contain a string field: description")

    frontmatter_text = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).rstrip()

    markdown = f"---\n{frontmatter_text}\n---\n\n{body}"

    if not markdown.endswith("\n"):
        markdown += "\n"

    return markdown


def write_skill_markdown(selector: str, data: Any, path: Path) -> None:
    """Write selected skill data as Markdown.

    If ``data`` is a single skill object, ``path`` is treated as a file unless it
    already exists as a directory.

    If ``data`` is a subtree containing multiple skill objects, ``path`` is
    treated as an output directory and namespace directories are preserved.
    """
    if is_skill_object(data):
        output = path

        if output.exists() and output.is_dir():
            output = output / f"{data['name']}.md"

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(skill_to_markdown(data), encoding="utf-8")
        return

    skills = list(iter_skill_objects(data, prefix=display_query_prefix(selector)))

    if not skills:
        raise ValueError("Selected skill query does not contain any skill objects")

    if path.exists() and not path.is_dir():
        raise ValueError(
            "Selected skill query resolved to a subtree, so --markdown PATH must be a directory"
        )

    path.mkdir(parents=True, exist_ok=True)

    for query_path, skill in skills:
        parts = [part for part in query_path.split(".") if part]
        if not parts:
            parts = [skill["name"]]

        output_dir = path.joinpath(*parts[:-1])
        output_dir.mkdir(parents=True, exist_ok=True)

        output = output_dir / f"{skill['name']}.md"
        output.write_text(skill_to_markdown(skill), encoding="utf-8")
