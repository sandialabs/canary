# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import copy
import os
import re
from collections import Counter
from typing import TYPE_CHECKING
from typing import Any

import yaml

from ..hookspec import hookimpl
from ..util import cpu_count
from ..util import logging
from .schemas import resource_pool_schema

if TYPE_CHECKING:
    from ..config import Config as CanaryConfig
    from ..config.argparsing import Parser
    from .rpool import ResourcePool


logger = logging.get_logger(__name__)
resource_regex = r"^([a-zA-Z_][a-zA-Z0-9_]*?)[:=](\d+)$"
_NODE_RESOURCE_TYPES = {"node", "nodes"}


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "-r",
        type=resource_t,
        action=update_action,
        dest="resource_pool_mods",
        metavar="TYPE=N",
        group="resource control",
        help=f"N instances of resource TYPE are available [default: cpus={cpu_count(logical=False)}]",
    )
    parser.add_argument(
        "--resource-pool-file",
        dest="resource_pool_file",
        metavar="FILE",
        group="resource control",
        help="Read resource pool from this JSON or YAML file",
    )
    parser.add_argument(
        "--oversubscribe",
        action=update_action,
        type=resource_t,
        metavar="TYPE=N",
        command=("run", "config"),
        group="resource control",
        help="Apply the multiplier N to the number of slots available "
        "per resource instance of type TYPE",
    )
    parser.add_argument(
        "--enable-hyperthreads",
        action="store_true",
        default=False,
        dest="resource_pool_enable_hyperthreads",
        group="resource control",
        help="Include hyperthreads in resource detection [default: %(default)s]",
    )


@hookimpl(trylast=True, specname="canary_resource_pool_fill")
def fill_default_node_local_pool(config: "CanaryConfig") -> dict[str, Any]:
    """Initialize the default single-node resource pool"""
    local: dict[str, Any] = {"id": os.uname().nodename}
    resources = local.setdefault("resources", {})
    ht: bool = config.getoption("resource_pool_enable_hyperthreads", False)
    cpus: int = int(var) if (var := os.getenv("CANARY_TESTING_CPUS")) else cpu_count(logical=ht)
    resources["cpus"] = [{"id": str(j), "slots": 1} for j in range(cpus)]
    gpus: int = int(var) if (var := os.getenv("CANARY_TESTING_GPUS")) else 0
    resources["gpus"] = [{"id": str(j), "slots": 1} for j in range(gpus)]
    pool: dict[str, Any] = {"additional_properties": {}, "nodes": [local]}
    return pool


@hookimpl(tryfirst=True, specname="canary_resource_pool_fill")
def fill_pool_from_file(config: "CanaryConfig") -> dict[str, Any] | None:
    f = config.getoption("resource_pool_file")
    if not f:
        return None

    data: dict
    with open(f) as fh:
        data = yaml.safe_load(fh)

    # Accept both:
    #
    #   resource_pool:
    #     nodes: ...
    #
    # and the raw resource-pool payload:
    #
    #   nodes: ...
    payload = data["resource_pool"] if "resource_pool" in data else data
    validated = resource_pool_schema.validate(payload)
    pool: dict[str, Any] = {}
    pool.update(validated)
    props = pool.setdefault("additional_properties", {})
    props["resource_pool_file"] = os.path.abspath(f)
    return pool


@hookimpl(trylast=True, specname="canary_resource_pool_update")
def finalize_resource_pool(config: "CanaryConfig", pool: "ResourcePool") -> None:
    """
    Apply command-line resource-pool modifiers.

    Semantics:

    - ``-r nodes=N`` sets the number of topology nodes.
    - ``-r TYPE=N`` sets N instances of TYPE on each node.
    - ``-r slots_per_TYPE=N`` multiplies slots on each resource instance of TYPE by N.
    - ``--oversubscribe TYPE=N`` is equivalent to ``slots_per_TYPE=N``.
    """
    errors = 0
    slots_per_rtype: Counter[str] = Counter()

    if rp := config.getoption("resource_pool_mods"):
        # First handle topology-level node count. This must happen before
        # resource-count overrides so that those overrides apply to every node.
        for key, count in rp.items():
            if not _is_node_type(key):
                continue

            try:
                _set_node_count(pool, count)
            except ValueError as e:
                errors += 1
                logger.error(str(e))
                continue

            if count > 1:
                pool.allow_multinode = True

        # Then apply resource-count overrides. These apply per node.
        for key, count in rp.items():
            if key.startswith("slots_per_") or _is_node_type(key):
                continue

            rtype = _normalize_resource_type(key)
            _set_resource_count(pool, rtype, count)

        # Then collect slots-per-resource overrides.
        for key, count in rp.items():
            if not key.startswith("slots_per_"):
                continue

            raw_rtype = key[10:]
            if _is_node_type(raw_rtype):
                errors += 1
                logger.error(f"Cannot define {key}={count}; nodes do not have slots")
                continue

            rtype = _normalize_resource_type(raw_rtype)
            if not _resource_type_defined(pool, rtype):
                errors += 1
                logger.error(
                    f"Cannot define {key}={count} since {rtype} "
                    "is not a defined resource pool member"
                )
                continue

            slots_per_rtype[rtype] = count

    if oversubscribe := config.getoption("oversubscribe"):
        for key, count in oversubscribe.items():
            if _is_node_type(key):
                errors += 1
                logger.error("--oversubscribe cannot be applied to nodes")
                continue

            rtype = _normalize_resource_type(key)
            if not _resource_type_defined(pool, rtype):
                errors += 1
                logger.error(
                    f"Cannot define --oversubscribe={key}:{count} since {rtype} "
                    "is not a defined resource pool member"
                )
                continue

            slots_per_rtype[rtype] = count

    if errors:
        raise ValueError("Stopping due to previous errors")

    for rtype, count in slots_per_rtype.items():
        _multiply_slots_per_resource(pool, rtype, count)


def _resource_specs(count: int) -> list[dict[str, Any]]:
    return [{"id": str(j), "slots": 1} for j in range(count)]


def _set_node_count(pool: "ResourcePool", count: int) -> None:
    from .rpool import Node

    if count < 1:
        raise ValueError("Resource pool must contain at least one node")

    if not pool.nodes:
        pool.nodes.append(Node(id=_local_node_id(), resources={}))

    if len(pool.nodes) > count:
        del pool.nodes[count:]
        _rebuild_node_index(pool)
        return

    template = pool.nodes[0]

    for i in range(len(pool.nodes), count):
        node = Node(
            id=str(i),
            resources=copy.deepcopy(template.resources),
            additional_properties=copy.deepcopy(template.additional_properties),
        )
        pool.nodes.append(node)

    _rebuild_node_index(pool)


def _set_resource_count(pool: "ResourcePool", rtype: str, count: int) -> None:
    specs = _resource_specs(count)

    for node in pool.nodes:
        node.resources[rtype] = copy.deepcopy(specs)
        node._recompute_slots()


def _multiply_slots_per_resource(pool: "ResourcePool", rtype: str, count: int) -> None:
    for node in pool.nodes:
        if rtype not in node.resources:
            continue

        for instance in node.resources[rtype]:
            instance["slots"] *= count

        node._recompute_slots()


def _resource_type_defined(pool: "ResourcePool", rtype: str) -> bool:
    return any(rtype in node.resources for node in pool.nodes)


def _rebuild_node_index(pool: "ResourcePool") -> None:
    pool._node_index.clear()

    for node in pool.nodes:
        if node.id in pool._node_index:
            raise ValueError(f"Duplicate node ID in resource pool: {node.id!r}")
        pool._node_index[node.id] = node


def _local_node_id() -> str:
    return os.uname().nodename


def _normalize_resource_type(rtype: str) -> str:
    if not rtype.endswith("s"):
        rtype += "s"
    return rtype


def _is_node_type(rtype: str) -> bool:
    return rtype in _NODE_RESOURCE_TYPES


def resource_t(arg: str) -> dict[str, int]:
    if match := re.search(resource_regex, arg):
        type = match.group(1)
        count = int(match.group(2))
        return {type: count}
    raise ValueError(f"Unable to determine resource type and count from {arg}")


class update_action(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        result = getattr(namespace, self.dest, None) or {}
        for key, value in values.items():
            result[key] = value
        setattr(namespace, self.dest, result)
