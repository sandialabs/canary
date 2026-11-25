# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Installed Canary knowledge: the capability and skill trees every provider contributes.

``canary learn`` / ``canary query -c|-k`` print them; ``/canary/query/capability`` and
``/canary/query/skills`` return them.
"""

from typing import Any

from .. import config
from ..config.schemas import capabilities_provider_schema
from ..config.schemas import skills_provider_schema
from ..util.query_data import display_query_prefix
from ..util.query_data import iter_skill_objects
from ..util.query_data import list_json_object_paths
from ..util.query_data import query_json


def capabilities(query: str = ".", *, list_keys: bool = False) -> Any:
    """The capability data at *query* (``ext.pyt.parameters``, ``core.hooks.post``, ...).

    A query outside a namespace is under ``core``; ``ext.`` selects the extensions'.  With
    *list_keys*, the queryable keys below *query* instead.

    Raises:
        KeyError, IndexError, TypeError: if *query* names nothing.
    """
    data, resolved = resolve_capabilities_query(build_capabilities_tree(), query)
    if list_keys:
        return list_capability_paths(data, resolved)
    return query_json(data, resolved)


def skills(query: str = ".", *, list_keys: bool = False) -> Any:
    """The skill data at *query* (``pyt.canary-pyt-authoring``, ...); *list_keys* as for
    :func:`capabilities`."""
    data = build_skills_tree()
    resolved = resolve_skills_query(data, query)
    if list_keys:
        return list_skill_paths(data, resolved)
    return query_json(data, resolved)


def resolve_capabilities_query(data: dict[str, Any], query: str) -> tuple[dict[str, Any], str]:
    if query in ("", "."):
        return data, "."

    if query == "ext":
        return extension_capabilities_tree(data), "."

    if query.startswith("ext."):
        return extension_capabilities_tree(data), query[4:]

    if query_targets_namespace(data, query):
        return data, query

    return data, f"core.{query}"


def resolve_skills_query(data: dict[str, Any], query: str) -> str:
    if query in ("", "."):
        return "."

    if query_targets_namespace(data, query):
        return query

    return f"core.{query}"


def extension_capabilities_tree(data: dict[str, Any]) -> dict[str, Any]:
    return {namespace: payload for namespace, payload in data.items() if namespace != "core"}


def query_targets_namespace(data: dict[str, Any], query: str) -> bool:
    if query.startswith("."):
        query = query[1:]

    if not query:
        return False

    if query.startswith("["):
        return False

    namespace = query.split(".", 1)[0]
    return namespace in data


def build_capabilities_tree() -> dict[str, Any]:
    """Build the runtime aggregate capabilities tree.

    Every provider contributes a document with a namespace. The aggregate shape is::

        {
          "core": {...},
          "pyt": {...},
          "vvtest": {...}
        }

    Providers may be backed by static JSON, dynamic Python dictionaries,
    introspection, or future external systems.

    """
    tree: dict[str, Any] = {}
    payloads = config.pluginmanager.hook.canary_capabilities()

    for payload in payloads:
        if payload is None:
            continue

        namespace, capabilities = normalize_capabilities_provider(payload)

        if namespace in tree:
            raise ValueError(f"Duplicate Canary capabilities namespace: {namespace}")

        tree[namespace] = capabilities

    return tree


def build_skills_tree() -> dict[str, Any]:
    """Build the runtime aggregate skills tree.

    Every provider contributes a document with a namespace. The aggregate shape is::

        {
          "core": {...},
          "pyt": {...},
          "vvtest": {...}
        }

    Providers may be backed by static JSON, dynamic Python dictionaries,
    introspection, or future external systems.

    """
    tree: dict[str, Any] = {}
    payloads = config.pluginmanager.hook.canary_skills()

    for payload in payloads:
        if payload is None:
            continue

        namespace, skills = normalize_skills_provider(payload)

        if namespace in tree:
            raise ValueError(f"Duplicate Canary skills namespace: {namespace}")

        tree[namespace] = skills

    return tree


def normalize_capabilities_provider(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate and normalize one capabilities provider payload."""
    document = capabilities_provider_schema.validate(payload)
    namespace = document["namespace"]
    capabilities = document["capabilities"]

    if not isinstance(capabilities, dict):
        raise TypeError(f"Capabilities payload for namespace {namespace!r} must be an object")

    return namespace, capabilities


def normalize_skills_provider(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate and normalize one skills provider payload."""
    document = skills_provider_schema.validate(payload)
    namespace = document["namespace"]
    skills = document["skills"]

    if not isinstance(skills, dict):
        raise TypeError(f"Skills payload for namespace {namespace!r} must be an object")

    return namespace, skills


def list_capability_paths(data: Any, query: str) -> list[str]:
    """List immediate queryable child object paths below a capabilities query point."""
    return list_json_object_paths(data, query)


def list_skill_paths(data: Any, query: str) -> list[str]:
    """List terminal skill object paths below a skill query point."""
    selected = query_json(data, query)
    prefix = display_query_prefix(query)

    rows: list[str] = []
    for path, _skill in iter_skill_objects(selected, prefix=prefix):
        rows.append(path)

    return sorted(rows)
