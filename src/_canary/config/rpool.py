# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import copy
import io
import pickle  # nosec B403
from typing import Any

import yaml

from ..error import ResourceUnsatisfiableError
from ..util import logging
from ..util.rprobe import cpu_count
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

    __slots__ = ("additional_properties", "resources")

    def __init__(self, pool: dict[str, Any] | None = None) -> None:
        self.additional_properties: dict[str, Any] = {}
        self.resources: dict[str, resource_spec] = {}
        if pool:
            self.fill(pool)

    def __repr__(self) -> str:
        pool = {"additional_properties": self.additional_properties, "resources": self.resources}
        fh = io.StringIO()
        yaml.dump({"resource_pool": pool}, fh, default_flow_style=False)
        return fh.getvalue()

    @property
    def types(self) -> set[str]:
        types: set[str] = {"cpus", "gpus"}
        types.update(self.resources.keys())
        return types

    def empty(self) -> bool:
        return len(self.resources) == 0

    def count(self, type: str) -> int:
        return len(self.resources[type])

    def fill(self, pool: dict[str, Any]) -> None:
        pool = resource_pool_schema.validate(pool)
        self.clear()
        if "additional_properties" in pool:
            self.additional_properties.update(pool["additional_properties"])
        self.resources.update(pool["resources"])

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
        slots_per_instance: dict[str, int] = {}
        if "cpus" not in kwds:
            kwds["cpus"] = cpu_count()
        for type, count in kwds.items():
            if type.startswith("slots_per_"):
                slots_per_instance[f"{type[10:]}s"] = count
        resources: dict[str, resource_spec] = {}
        for type, count in kwds.items():
            if type.startswith("slots_per_"):
                continue
            slots = slots_per_instance.get(type, 1)
            resources[type] = [{"id": str(j), "slots": slots} for j in range(count)]
        self.fill({"resources": resources, "additional_properties": {}})

    def modify(self, **kwds: int) -> None:
        for type, count in kwds.items():
            if type.startswith("slots_per_"):
                continue
            self.resources[type] = [{"id": str(j), "slots": 1} for j in range(count)]
        for key, count in kwds.items():
            if key.startswith("slots_per_"):
                type = f"{key[10:]}s"
                for instance in self.resources[type]:
                    instance["slots"] = count

    def satisfiable(self, required: list[list[dict[str, Any]]]) -> bool:
        """determine if the resources for this test are satisfiable"""
        if self.empty():
            raise EmptyResourcePoolError
        slots_reqd: dict[str, int] = {}
        for group in required:
            for item in group:
                type = item["type"]
                if item["type"] not in self.resources:
                    msg = f"required resource type {type!r} is not registered with canary"
                    raise ResourceUnsatisfiableError(msg)
                slots_reqd[type] = slots_reqd.get(type, 0) + item["slots"]
        for type, slots in slots_reqd.items():
            spec = self.resources[type]
            slots_avail = sum([_["slots"] for _ in spec])
            if slots_avail < slots:
                raise ResourceUnsatisfiableError(f"insufficient slots of {type!r} available")
        return True

    def acquire(self, required: list[list[dict[str, Any]]]) -> list[dict[str, list[dict]]]:
        """Returns resources available to the test

        local[i] = {<type>: [{'id': <id>, 'slots': <slots>}, ...], ... }

        """
        if self.empty():
            raise EmptyResourcePoolError
        totals: dict[str, int] = {}
        acquired: list[dict[str, list[dict]]] = []
        try:
            stash: bytes = pickle.dumps(self.resources)  # nosec B301
            for group in required:
                # {type: [{id: ..., slots: ...}]}
                local: dict[str, list[dict]] = {}
                for item in group:
                    type, slots = item["type"], item["slots"]
                    if type not in self.resources:
                        raise TypeError(f"unknown resource requirement type {type!r}")
                    rspec = self._get_from_pool(item["type"], item["slots"])
                    local.setdefault(type, []).append(rspec)
                    totals[type] = totals.get(type, 0) + slots
                acquired.append(local)
        except Exception:
            self.resources.clear()
            self.resources.update(pickle.loads(stash))  # nosec B301
            raise
        if logging.get_level() <= logging.DEBUG:
            for type, n in totals.items():
                N = sum([instance["slots"] for instance in self.resources[type]]) + n  # type: ignore[misc]
                if n == 1 and type.endswith("s"):
                    type = type[:-1]
                logger.debug(f"Acquiring {n} {type} from {N} available")
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
                if n == 1 and type.endswith("s"):
                    type = type[:-1]
                logger.debug(f"Reclaimed {n} {type}")

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
