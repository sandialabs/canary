# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import copy
import math
import pickle
from typing import Any
from typing import Iterable

from ..util import logging
from ..util.rprobe import cpu_count


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

    __slots__ = ("map", "pool", "types", "_stash", "slots_per")

    def __init__(self, pool: list[dict[str, Any]] | None = None) -> None:
        self.map: dict[str, dict[tuple[str, str], int]] = {}
        self.pool: list[dict[str, Any]] = []
        self.types: set[str] = {"cpus", "gpus"}
        self._stash: bytes | None = None
        self.slots_per: dict[str, int] = {}
        if pool:
            self.fill(pool)
        else:
            self.fill_uniform(node_count=1, cpus_per_node=cpu_count(), gpus_per_node=0)

    def update(self, *args: Any, **kwargs: Any) -> None:
        self.fill(args[0])

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
                for instance in instances:
                    lid = instance["id"]
                    slots += instance["slots"]
                    gid = gids.setdefault(type, 0)
                    self.map.setdefault(type, {})[(pid, lid)] = gid
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
                if key := contains(local, (arg, f"{arg}s")):
                    return len(local[key])
            return 0
        if item.endswith("_count"):
            count = 0
            arg = item[:-6]
            for local in self.pool:
                if key := contains(local, (arg, f"{arg}s")):
                    count += len(local[key])
            return count
        raise KeyError(item)

    def getstate(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.pool)

    def gid(self, type: str, pid: str, lid: str) -> int:
        return self.map[type][(pid, lid)]

    def local_ids(self, type: str, arg_gid: int) -> tuple[str, str]:
        for key, gid in self.map[type].items():
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
        self.map.clear()
        self.pool.clear()
        self.types.clear()
        self.slots_per.clear()

    def fill_uniform(self, *, node_count: int, cpus_per_node: int, **kwds: int) -> None:
        pool: list[dict[str, Any]] = []
        for i in range(node_count):
            local: dict[str, Any] = {}
            for j in range(cpus_per_node):
                local.setdefault("cpus", []).append({"id": str(j), "slots": 1})
            for name, count in kwds.items():
                if name.endswith("_per_node"):
                    for j in range(count):
                        local.setdefault(name[:-9], []).append({"id": str(j), "slots": 1})
            local["id"] = str(i)
            pool.append(local)
        self.fill(pool)

    def stash(self) -> None:
        # pickling faster than taking a deep copy of the pool
        self._stash = pickle.dumps(self.pool)

    def unstash(self) -> None:
        assert self._stash is not None
        self.pool.clear()
        self.pool.extend(pickle.loads(self._stash))
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
        if logging.LEVEL <= logging.DEBUG:
            for type, n in totals.items():
                N = sum([_["slots"] for local in self.pool for _ in local[type]]) + n
                if n == 1 and type.endswith("s"):
                    type = type[:-1]
                logging.debug(f"Acquiring {n} {type} from {N} available")
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
        if logging.LEVEL <= logging.DEBUG:
            for type, n in types.items():
                if n == 1 and type.endswith("s"):
                    type = type[:-1]
                logging.debug(f"Reclaimed {n} {type}")


def contains(sequence: Iterable[Any], args: tuple[Any, ...]) -> Any:
    for arg in args:
        if arg in sequence:
            return arg
    return None


class ResourceUnsatisfiable(Exception):
    pass


class ResourceUnavailable(Exception):
    pass
