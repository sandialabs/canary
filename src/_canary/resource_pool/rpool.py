# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import copy
import io
import pickle  # nosec B403
from collections import Counter
from typing import IO
from typing import TYPE_CHECKING
from typing import Any

import yaml

from ..util import cpu_count
from ..util import logging
from ..util.string import pluralize
from .schemas import resource_pool_schema

if TYPE_CHECKING:
    from ..config import Config as CanaryConfig

logger = logging.get_logger(__name__)

resource_spec = list[dict[str, str | int]]


class Outcome:
    __slots__ = ("ok", "reason")

    def __init__(self, ok: bool | None = None, reason: str | None = None) -> None:
        if not ok:
            ok = not bool(reason)
        if not ok and not reason:
            raise ValueError(f"{self.__class__.__name__}(False) requires a reason")
        self.ok: bool = ok
        self.reason: str | None = reason

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        state = "ok" if self.ok else "fail"
        reason = f": {self.reason}" if self.reason else ""
        return f"<{self.__class__.__name__} {state}{reason}>"


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
        file = io.StringIO()
        self.dump(file)
        return file.getvalue()

    def __contains__(self, type: str) -> bool:
        return type in self.resources

    def dump(self, file: IO[Any]) -> None:
        pool = {"additional_properties": self.additional_properties, "resources": self.resources}
        yaml.dump({"resource_pool": pool}, file, default_flow_style=False)

    @property
    def types(self) -> list[str]:
        return sorted(self.resources.keys())

    def empty(self) -> bool:
        return len(self.resources) == 0

    def count(self, type: str) -> int:
        if type in ("node", "nodes"):
            node_info: dict = self.additional_properties.setdefault("nodes", {})
            return node_info.setdefault("count", 1)
        if type in self.resources:
            return len(self.resources[type])
        elif f"{type}s" in self.resources:
            return len(self.resources[f"{type}s"])
        raise ResourceUnavailable(type)

    def fill(self, pool: dict[str, Any]) -> None:
        pool = resource_pool_schema.validate(pool)
        self.clear()
        if "additional_properties" in pool:
            self.additional_properties.update(pool["additional_properties"])
        if "gpus" not in pool["resources"]:
            pool["resources"]["gpus"] = []
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
            kwds["cpus"] = cpu_count()
        if "gpus" not in kwds:
            kwds["gpus"] = 0
        resources: dict[str, resource_spec] = {}
        for type, count in kwds.items():
            resources[type] = [{"id": str(j), "slots": 1} for j in range(count)]
        self.fill({"resources": resources, "additional_properties": {}})

    def accommodates(self, request: list[dict[str, Any]]) -> Outcome:
        """determine if the resources for this test are available"""
        if self.empty():
            raise EmptyResourcePoolError

        slots_needed: Counter[str] = Counter()
        missing: set[str] = set()

        # Step 1: Gather resource requirements and detect missing types
        for member in request:
            rtype = member["type"]
            if rtype in self.resources:
                slots_needed[rtype] += member["slots"]
            else:
                missing.add(rtype)
        if missing:
            types = "[bold]%s[/]" % ",".join(sorted(missing))
            key = pluralize("Resource", n=len(missing))
            return Outcome(False, reason=f"{key} unavailable: {types}")

        # Step 2: Check available slots vs. needed slots
        wanting: dict[str, tuple[int, int]] = {}
        for rtype, slots in slots_needed.items():
            slots_avail = self.slots_per_resource_type[rtype]
            if slots_avail < slots:
                wanting[rtype] = (slots, slots_avail)
        if wanting:
            reason: str
            levelno: int = logging.get_level()
            if levelno <= logging.DEBUG:
                t = "[bold]%s[/] (requested %d, available %d)"
                types = ", ".join(t % (k, *wanting[k]) for k in sorted(wanting))
                reason = f"insufficient slots of {types}"
            else:
                types = ", ".join("[bold]%s[/]" % t for t in wanting)
                reason = f"insufficient slots of {types}"
            return Outcome(False, reason=reason)

        # Step 3: all good
        return Outcome(True)

    def checkout(self, request: list[dict[str, Any]], **kwds: Any) -> dict[str, list[dict]]:
        """Returns resources available to the test

        local[i] = {<type>: [{'id': <id>, 'slots': <slots>}, ...], ... }

        """
        if self.empty():
            raise EmptyResourcePoolError
        totals: Counter[str] = Counter()
        acquired: dict[str, list[dict]] = {}
        stash: bytes = pickle.dumps(self.resources)  # nosec B301
        try:
            for item in request:
                # {type: [{id: ..., slots: ...}]}
                rtype, slots = item["type"], item["slots"]
                if rtype not in self.resources:
                    raise TypeError(f"Unknown resource requirement type {rtype!r}")
                rspec = self._get_from_pool(rtype, slots)
                acquired.setdefault(rtype, []).append(rspec)
                totals[rtype] += slots
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

    def checkin(self, resources: dict[str, list[dict]]) -> None:
        types: Counter[str] = Counter()
        for type, rspecs in resources.items():
            for rspec in rspecs:
                n = self._return_to_pool(type, rspec)
                types[type] += n
        if logging.get_level() <= logging.DEBUG:
            for type, n in types.items():
                key = type[:-1] if n == 1 and type.endswith("s") else type
                logger.debug(f"Checked in {n} {key}")

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
        raise ValueError(f"Attempting to checkin a resource whose ID is unknown: {rspec!r}")


def make_resource_pool(config: "CanaryConfig"):
    pool: dict[str, dict[str, Any]] = {"resources": {}, "additional_properties": {}}
    config.pluginmanager.hook.canary_resource_pool_fill(config=config, pool=pool)
    pool = resource_pool_schema.validate(pool)
    return ResourcePool(pool)


class ResourceUnavailable(Exception):
    pass


class EmptyResourcePoolError(Exception):
    pass
