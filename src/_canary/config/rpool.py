# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import copy
import io
import pickle  # nosec B403
from collections import Counter
from typing import Any

import psutil
import yaml

from ..error import ResourceUnsatisfiableError
from ..util import logging
from .schemas import resource_pool_schema

logger = logging.get_logger(__name__)

resource_spec = list[dict[str, str | int]]


class ResourcePool:
    """Class representing resources available on the computer

    Args:
      pool: The resource pool specification

    Resource specification
    ----------------------

    The specification for the resource pool is adopted from the ctest schema:

    .. code-block:: yaml

        local:
          <resource name>:
          - id: str
            slots: int

    For example, a machine with 4 GPUs may have

    .. code-block:: yaml

        local:
          gpus:
          - id: "01"
            slots: 1
          - id: "02"
            slots: 1
          - id: "03"
            slots: 1
          - id: "04"
            slots: 1

    canary adopts a similar layout:

    .. code-block:: yaml

        resource_pool:
          additional_properties: {}
          resources:
            <resource name>:
            - id: str
              slots: int
            ...

    For example, a machine having 8 CPUs and 4 GPUs may have

    .. code-block:: yaml

        resource_pool:
          additional_properties: {}
          resources:
            gpus:
            - id: "01"
              slots: 1
            - id: "02"
              slots: 1
            - id: "03"
              slots: 1
            - id: "04"
              slots: 1
            cpus:
            - id: "01"
              slots: 1
            - id: "02"
              slots: 1
            - id: "03"
              slots: 1
            - id: "04"
              slots: 1
            - id: "05"
              slots: 1
            - id: "06"
              slots: 1
            - id: "07"
              slots: 1
            - id: "08"
              slots: 1

    """

    __slots__ = ("additional_properties", "resources", "slots_per_resource_type")

    def __init__(self, pool: dict[str, Any] | None = None) -> None:
        self.additional_properties: dict[str, Any] = {}
        self.resources: dict[str, resource_spec] = {}
        self.slots_per_resource_type: Counter[str] = Counter()
        if pool:
            self.fill(pool)

    def __repr__(self) -> str:
        pool = {"additional_properties": self.additional_properties, "resources": self.resources}
        fh = io.StringIO()
        yaml.dump({"resource_pool": pool}, fh, default_flow_style=False)
        return fh.getvalue()

    def __contains__(self, type: str) -> bool:
        return type in self.resources

    @property
    def types(self) -> list[str]:
        types: set[str] = {"cpus", "gpus"}
        types.update(self.resources.keys())
        return sorted(types)

    def empty(self) -> bool:
        return len(self.resources) == 0

    def count(self, type: str) -> int:
        if type in ("node", "nodes"):
            return 1
        if type in self.resources:
            return len(self.resources[type])
        elif f"{type}s" in self.resources:
            return len(self.resources[f"{type}s"])
        raise ResourceUnavailable(type)

    def slots(self, type: str) -> int:
        return self.slots_per_resource_type[type]

    def fill(self, pool: dict[str, Any]) -> None:
        pool = resource_pool_schema.validate(pool)
        self.clear()
        if "additional_properties" in pool:
            self.additional_properties.update(pool["additional_properties"])
        self.resources.update(pool["resources"])
        for type, instances in pool["resources"].items():
            self.slots_per_resource_type[type] = sum([_["slots"] for _ in instances])

    def pop(self, type: str) -> resource_spec | None:
        if type in self.resources:
            del self.slots_per_resource_type[type]
            return self.resources.pop(type)
        return None

    def getstate(self) -> dict[str, Any]:
        state = {
            "additional_properties": copy.deepcopy(self.additional_properties),
            "resources": copy.deepcopy(self.resources),
        }
        return state

    def clear(self) -> None:
        self.resources.clear()
        self.additional_properties.clear()

    def populate(self, **kwds: int) -> None:
        if "cpus" not in kwds:
            kwds["cpus"] = psutil.cpu_count()
        resources: dict[str, resource_spec] = {}
        for type, count in kwds.items():
            resources[type] = [{"id": str(j), "slots": 1} for j in range(count)]
        self.fill({"resources": resources, "additional_properties": {}})

    def modify(self, **kwds: int) -> None:
        for type, count in kwds.items():
            self.resources[type] = [{"id": str(j), "slots": 1} for j in range(count)]
        for type in kwds:
            self.slots_per_resource_type[type] = sum([_["slots"] for _ in self.resources[type]])

    def accommodates(self, resource_groups: list[list[dict[str, Any]]]) -> bool:
        """determine if the resources for this test are available"""
        if self.empty():
            raise EmptyResourcePoolError
        slots_needed: Counter[str] = Counter()
        for group in resource_groups:
            for member in group:
                rtype = member["type"]
                if rtype not in self.resources:
                    msg = f"required resource type {rtype!r} is not registered with canary"
                    raise ResourceUnavailable(msg)
                slots_needed[rtype] += member["slots"]
        for rtype, slots in slots_needed.items():
            slots_avail = self.slots(rtype)
            if slots_avail < slots:
                raise ResourceUnsatisfiableError(
                    f"insufficient slots of {rtype!r} available, "
                    f"requested: {slots}, available: {slots_avail}"
                )
        return True

    def acquire(self, resource_groups: list[list[dict[str, Any]]]) -> list[dict[str, list[dict]]]:
        """Returns resources available to the test

        local[i] = {<type>: [{'id': <id>, 'slots': <slots>}, ...], ... }

        """
        if self.empty():
            raise EmptyResourcePoolError
        totals: Counter[str] = Counter()
        acquired: list[dict[str, list[dict]]] = []
        try:
            stash: bytes = pickle.dumps(self.resources)  # nosec B301
            for group in resource_groups:
                # {type: [{id: ..., slots: ...}]}
                local: dict[str, list[dict]] = {}
                for member in group:
                    rtype, slots = member["type"], member["slots"]
                    if rtype not in self.resources:
                        raise TypeError(f"Unknown resource requirement type {rtype!r}")
                    rspec = self._get_from_pool(rtype, slots)
                    local.setdefault(rtype, []).append(rspec)
                    totals[rtype] += slots
                acquired.append(local)
        except Exception:
            self.resources.clear()
            self.resources.update(pickle.loads(stash))  # nosec B301
            raise
        if logging.get_level() <= logging.DEBUG:
            for rtype, n in totals.items():
                N = sum([instance["slots"] for instance in self.resources[rtype]]) + n  # type: ignore[misc]
                key = rtype[:-1] if n == 1 and rtype.endswith("s") else rtype
                logger.debug(f"Acquiring {n} {key} from {N} available")
        return acquired

    def reclaim(self, resources: list[dict[str, list[dict]]]) -> None:
        types: dict[str, int] = {}
        for resource in resources:  # list[dict[str, list[dict]]]) -> None:
            for type, rspecs in resource.items():
                for rspec in rspecs:
                    n = self._return_to_pool(type, rspec)
                    types[type] = types.setdefault(type, 0) + n
        if logging.get_level() <= logging.DEBUG:
            for type, n in types.items():
                key = type[:-1] if n == 1 and type.endswith("s") else type
                logger.debug(f"Reclaimed {n} {key}")

    def _get_from_pool(self, type: str, slots: int) -> dict[str, Any]:
        instances = sorted(self.resources[type], key=lambda x: x["slots"])
        for instance in instances:
            if slots <= instance["slots"]:  # type: ignore[operator]
                instance["slots"] -= slots  # type: ignore[operator]
                rspec: dict[str, Any] = {"id": instance["id"], "slots": slots}
                return rspec
        raise ResourceUnavailable

    def _return_to_pool(self, type: str, rspec: dict[str, Any]) -> int:
        for instance in self.resources[type]:
            if instance["id"] == rspec["id"]:
                slots = rspec["slots"]
                instance["slots"] += slots
                return slots
        raise ValueError(f"Attempting to reclaim a resource whose ID is unknown: {rspec!r}")


class ResourceUnavailable(Exception):
    pass


class EmptyResourcePoolError(Exception):
    pass
