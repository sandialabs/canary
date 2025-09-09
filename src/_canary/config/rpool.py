# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import copy
import math
import pickle  # nosec B403
from typing import Any

from ..util import logging
from ..util.collections import contains_any
from ..util.rprobe import cpu_count
from .schemas import resource_schema as schema

logger = logging.get_logger(__name__)


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

    canary adopts a similar layout to work on multi-node systems by allowing for a list of
    objects (similar to ctest's ``local``) each with its own ``id``:

    .. code-block:: yaml

        resource_pool:
        - id: str
          <resource name>:
          - id: str
            slots: int

    For example, a machine having 2 nodes with 4 GPUs per node may have

    .. code-block:: yaml

        resource_pool:
        - id: "01"
          gpus:
          - id: "01"
            slots: 1
          - id: "02"
            slots: 1
          - id: "03"
            slots: 1
          - id: "04"
            slots: 1
        - id: "02"
          gpus:
          - id: "01"
            slots: 1
          - id: "02"
            slots: 1
          - id: "03"
            slots: 1
          - id: "04"
            slots: 1

    Resource allocation
    -------------------

    Resources are allocated from a global resource pool that is generated from the list of ``node``
    resource specifications.  A global-to-local mapping is maintained which maps the global resource
    ID understood by ``canary`` to the local resource ID given in the ``node`` resource spec.
    E.g., ``gid = map[type][(pid, lid)]``.

    Internal representation
    -----------------------

    Internally, the pool of resources is stored as a dictionary with layout (eg, for the example
    above):

    .. code-block:: python

       pool = [
         {
           "id": "01",
           "gpus": [
             {"id": "01", "slots": 1},
             {"id": "02", "slots": 1},
             {"id": "03", "slots": 1},
             {"id": "04", "slots": 1},
           ]
         }
       ]

    """

    __slots__ = ("maps", "pool", "types", "_stash", "slots_per")

    def __init__(self, pool: list[dict[str, Any]] | None = None) -> None:
        self.maps: dict[str, dict[tuple[str, str], int]] = {}
        self.pool: list[dict[str, Any]] = []
        self.types: set[str] = {"cpus", "gpus"}
        self._stash: bytes | None = None
        self.slots_per: dict[str, int] = {}
        if pool:
            self.fill(pool)

    def __repr__(self) -> str:
        import io

        import yaml

        fh = io.StringIO()
        yaml.dump(self.pool, fh)
        return fh.getvalue()

    def empty(self) -> bool:
        return len(self.pool) == 0

    def update(self, *args: Any, **kwargs: Any) -> None:
        self.fill(args[0])

    def add(self, **mods: Any) -> None:
        """Add a resource to the pool"""
        if contains_any(mods, "local", "nodes", "node_count"):
            # Modifications are requesting a new node layout
            pool = schema.validate({"resource_pool": mods})["resource_pool"]
            self.clear()
            self.fill(pool)
            return
        for kwd in mods:
            if not kwd.endswith("s") and not kwd.endswith("_per_node"):
                raise TypeError(f"ResourcePool.add() got an unexpected keyword argument {kwd!r}")

        if self.empty():

            def f(d: dict[str, Any], key: str, default: int) -> int:
                if key in d:
                    return d.pop(key)
                if f"{key}_per_node" in d:
                    return d.pop(f"{key}_per_node")
                return default

            cpus_per_node = f(mods, "cpus", cpu_count())
            gpus_per_node = f(mods, "gpus", 0)
            self.fill_uniform(
                node_count=1, cpus_per_node=cpus_per_node, gpus_per_node=gpus_per_node, **mods
            )

        for kwd, count in mods.items():
            type = kwd[:-9] if kwd.endswith("_per_node") else kwd
            if self.slots_per.get(type, 0) > 0:
                raise ValueError(f"resource {type} already exists in pool")
            if not isinstance(count, int):
                raise ValueError(f"expected {kwd} count to be an integeger")
            if count < 0:
                raise ValueError(f"expected {type} count >= 0, got {count=}")
            self.types.add(type)
            map = self.maps.setdefault(type, {})
            gid = 0 if not map else (max(map.values()) + 1)
            slots = self.slots_per.get(type, 0)
            for local in self.pool:
                pid = local["id"]
                for i in range(count):
                    lid = str(i)
                    local.setdefault(type, []).append({"id": lid, "slots": 1})
                    map[(pid, lid)] = gid
                    gid += 1
                slots += count
            self.slots_per[type] = slots

    def fill(self, pool: list[dict[str, Any]]) -> None:
        self.clear()
        gids: dict[str, int] = {}
        for i, local in enumerate(pool):
            pid = str(local.pop("id", i))
            if "cpus" not in local:
                raise TypeError(f"required resource 'cpus' not defined in pool instance {i}")
            if "gpus" not in local:
                local["gpus"] = []
            # fraction usable
            for type, instances in local.items():
                self.types.add(type)
                slots = self.slots_per.get(type, 0)
                map = self.maps.setdefault(type, {})
                for instance in instances:
                    lid = instance["id"]
                    slots += instance["slots"]
                    gid = gids.setdefault(type, 0)
                    map[(pid, lid)] = gid
                    gids[type] += 1
                self.slots_per[type] = slots
            local["id"] = pid
            self.pool.append(local)

    def pinfo(self, item: str) -> Any:
        if item == "node_count":
            return len(self.pool)
        if item.endswith("_per_node"):
            arg = item[:-9]
            for local in self.pool:
                if key := contains_any(local, arg, f"{arg}s"):
                    return len(local[key])
            return 0
        if item.endswith("_count"):
            count = 0
            arg = item[:-6]
            for local in self.pool:
                if key := contains_any(local, arg, f"{arg}s"):
                    count += len(local[key])
            return count
        raise KeyError(item)

    def getstate(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.pool)

    def gid(self, type: str, pid: str, lid: str) -> int:
        return self.maps[type][(pid, lid)]

    def local_ids(self, type: str, arg_gid: int) -> tuple[str, str]:
        for key, gid in self.maps[type].items():
            if arg_gid == gid:
                return key[0], key[1]
        raise KeyError((type, arg_gid))

    def nodes_required(self, required: list[list[dict[str, Any]]]) -> int:
        """Determine the number of nodes required by ``obj``"""
        node_count: int = 1
        for group in required:
            for type in self.types:
                count: int = 0
                count_per_node = len(self.pool[0][type])
                for item in group:
                    if item["type"] == type:
                        count += item["slots"]
                if count_per_node and count:
                    node_count = max(math.ceil(count / count_per_node), node_count)
        return node_count

    def clear(self) -> None:
        self.maps.clear()
        self.pool.clear()
        self.types.clear()
        self.slots_per.clear()

    def fill_default(self) -> None:
        self.clear()
        self.fill_uniform(node_count=1, cpus_per_node=cpu_count(), gpus_per_node=0)

    def fill_uniform(self, *, node_count: int, cpus_per_node: int, **kwds: int) -> None:
        pool: list[dict[str, Any]] = []
        for i in range(node_count):
            local: dict[str, Any] = {}
            local["cpus"] = [{"id": str(j), "slots": 1} for j in range(cpus_per_node)]
            for kwd, count in kwds.items():
                if not kwd.endswith("_per_node"):
                    raise TypeError(
                        f"ResourcePool.fill_uniform() got an unexpected keyword argument {kwd!r} "
                        "(all keyword arguments are expected to end in '_per_node')"
                    )
                local[kwd[:-9]] = [{"id": str(j), "slots": 1} for j in range(count)]
            local["id"] = str(i)
            pool.append(local)
        self.fill(pool)

    def stash(self) -> None:
        # pickling faster than taking a deep copy of the pool
        self._stash = pickle.dumps(self.pool)  # nosec B301

    def unstash(self) -> None:
        # NOTE: pickled data is process-internal and not loaded from untrusted sources
        assert self._stash is not None
        self.pool.clear()
        self.pool.extend(pickle.loads(self._stash))  # nosec B301
        self._stash = None

    def _get_from_pool(self, type: str, slots: int) -> dict[str, Any]:
        for local in self.pool:
            instances = sorted(local[type], key=lambda x: x["slots"])
            for instance in instances:
                if slots <= instance["slots"]:
                    instance["slots"] -= slots
                    gid = self.gid(type, local["id"], instance["id"])
                    return {"gid": gid, "slots": slots}
        raise ResourceUnavailable

    def satisfiable(self, required: list[list[dict[str, Any]]]) -> None:
        """determine if the resources for this test are satisfiable"""
        if self.empty():
            raise EmptyResourcePoolError
        slots_reqd: dict[str, int] = {}
        for group in required:
            for item in group:
                if item["type"] not in self.types:
                    t = item["type"]
                    msg = f"required resource type {t!r} is not registered with canary"
                    raise ResourceUnsatisfiable(msg)
                slots_reqd[item["type"]] = slots_reqd.get(item["type"], 0) + item["slots"]
        for type, slots in slots_reqd.items():
            if self.slots_per[type] < slots:
                msg = f"insufficient slots of {type!r} available"
                raise ResourceUnsatisfiable(msg) from None

    def acquire(self, required: list[list[dict[str, Any]]]) -> list[dict[str, list[dict]]]:
        """Returns resources available to the test

        local[i] = {<type>: [{'gid': <gid>, 'slots': <slots>}, ...], ... }

        """
        if self.empty():
            raise EmptyResourcePoolError
        totals: dict[str, int] = {}
        acquired: list[dict[str, list[dict]]] = []
        try:
            self.stash()
            for group in required:
                # {type: [{gid: ..., slots: ...}]}
                local: dict[str, list[dict]] = {}
                for item in group:
                    type, slots = item["type"], item["slots"]
                    if type not in self.types:
                        raise TypeError(f"unknown resource requirement type {type!r}")
                    r = self._get_from_pool(item["type"], item["slots"])
                    items = local.setdefault(type, [])
                    items.append(r)
                    totals[type] = totals.get(type, 0) + slots
                acquired.append(local)
        except Exception:
            self.unstash()
            raise
        else:
            self._stash = None
        if logging.get_level() <= logging.DEBUG:
            for type, n in totals.items():
                N = sum([_["slots"] for local in self.pool for _ in local[type]]) + n
                if n == 1 and type.endswith("s"):
                    type = type[:-1]
                logger.debug(f"Acquiring {n} {type} from {N} available")
        return acquired

    def reclaim(self, resources: list[dict[str, list[dict]]]) -> None:
        def _reclaim(type, rspec):
            pid, lid = self.local_ids(type, rspec["gid"])
            for local in self.pool:
                if local["id"] == pid:
                    for instance in local[type]:
                        if instance["id"] == lid:
                            slots = rspec["slots"]
                            instance["slots"] += slots
                            return slots
            raise ValueError(f"Attempting to reclaim a resource whose ID is unknown: {rspec!r}")

        types: dict[str, int] = {}
        for resource in resources:  # list[dict[str, list[dict]]]) -> None:
            for type, rspecs in resource.items():
                for rspec in rspecs:
                    n = _reclaim(type, rspec)
                    types[type] = types.setdefault(type, 0) + n
        if logging.get_level() <= logging.DEBUG:
            for type, n in types.items():
                if n == 1 and type.endswith("s"):
                    type = type[:-1]
                logger.debug(f"Reclaimed {n} {type}")


class ResourceUnsatisfiable(Exception):
    pass


class ResourceUnavailable(Exception):
    pass


class EmptyResourcePoolError(Exception):
    pass
