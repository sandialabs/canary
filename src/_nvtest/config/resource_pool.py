import copy
import math
import pickle
from typing import TYPE_CHECKING
from typing import Any

from ..util import logging

if TYPE_CHECKING:
    from ..test.atc import AbstractTestCase


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

    nvtest adopts a similar layout to work on multi-node systems by allowing for a list of
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
    ID understood by ``nvtest`` to the local resource ID given in the ``node`` resource spec.
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

    __slots__ = ("map", "pool", "types", "_stash")

    def __init__(self, pool: list[dict[str, Any]] | None = None) -> None:
        self.map: dict[str, dict[tuple[str, str], int]] = {}
        self.pool: list[dict[str, Any]] = []
        self.types: set[str] = {"cpus", "gpus"}
        self._stash: bytes | None = None
        if pool:
            self.fill(pool)

    def update(self, *args: Any, **kwargs: Any) -> None:
        self.fill(args[0])

    def fill(self, pool: list[dict[str, Any]]) -> None:
        self.clear()
        gids: dict[str, int] = {}
        for i, spec in enumerate(pool):
            pid = str(spec.pop("id", i))
            if "cpus" not in spec:
                raise TypeError(f"required resource 'cpus' not defined in pool instance {i}")
            if "gpus" not in spec:
                spec["gpus"] = []
            for type, instances in spec.items():
                self.types.add(type)
                for instance in instances:
                    lid = instance["id"]
                    gid = gids.setdefault(type, 0)
                    self.map.setdefault(type, {})[(pid, lid)] = gid
                    gids[type] += 1
            spec["id"] = pid
            self.pool.append(spec)

    def pinfo(self, item: str) -> Any:
        if item == "node_count":
            return len(self.pool)
        if item.endswith("_per_node"):
            key = item[:-9]
            for spec in self.pool:
                if key in spec:
                    return len(spec[key])
            return 0
        if item.endswith("_count"):
            key = item[:-6] + "s"
            count = 0
            for spec in self.pool:
                if key in spec:
                    count += len(spec[key])
            return 0
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

    def min_nodes_required(self, obj: "AbstractTestCase") -> int:
        """Determine the number of nodes required by ``obj``"""
        node_count: int = 1
        for case in obj:
            required = case.required_resources()
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

    def fill_uniform(self, *, node_count: int, cpus_per_node: int, **kwds: int) -> None:
        pool: list[dict[str, Any]] = []
        for i in range(node_count):
            spec: dict[str, Any] = {}
            for j in range(cpus_per_node):
                spec.setdefault("cpus", []).append({"id": str(j), "slots": 1})
            for name, count in kwds.items():
                if name.endswith("_per_node"):
                    for j in range(count):
                        spec.setdefault(name[:-9], []).append({"id": str(j), "slots": 1})
            spec["id"] = str(i)
            pool.append(spec)
        self.fill(pool)

    def stash(self) -> None:
        # pickling faster than taking a deep copy of the pool
        self._stash = pickle.dumps(self.pool)

    def unstash(self) -> None:
        assert self._stash is not None
        self.pool.clear()
        self.pool.extend(pickle.loads(self._stash))
        self._stash = None

    def satisfiable(self, obj: "AbstractTestCase") -> None:
        """determine if the resources for this test are satisfiable"""
        required = obj.required_resources()
        try:
            self.stash()
            for group in required:
                for item in group:
                    if item["type"] not in self.types:
                        t = item["type"]
                        msg = f"required resource type {t!r} is not registered with nvtest"
                        raise ResourceUnsatisfiable(msg)
                    try:
                        self._get_from_pool(item["type"], item["slots"])
                    except ResourceUnavailable:
                        t = item["type"]
                        msg = f"insufficient slots of {t!r} available"
                        raise ResourceUnsatisfiable(msg) from None
        finally:
            self.unstash()

    def _get_from_pool(self, type: str, slots: int) -> dict[str, Any]:
        for spec in self.pool:
            for name, instances in spec.items():
                if type == name:
                    for instance in sorted(instances, key=lambda x: x["slots"]):
                        if slots <= instance["slots"]:
                            instance["slots"] -= slots
                            gid = self.gid(type, spec["id"], instance["id"])
                            return {"gid": gid, "slots": slots}
        raise ResourceUnavailable

    def acquire(self, obj: "AbstractTestCase") -> None:
        """Returns resources available to the test

        specs[i] = {<type>: [{'gid': <gid>, 'slots': <slots>}, ...], ... }

        """
        totals: dict[str, int] = {}
        required = obj.required_resources()
        if not required:
            raise ValueError(f"{obj}: no resources requested, a test should require at least 1 cpu")
        resource_specs: list[dict[str, list[dict]]] = []
        try:
            self.stash()
            for group in required:
                # {type: [{gid: ..., slots: ...}]}
                spec: dict[str, list[dict]] = {}
                for item in group:
                    type, slots = item["type"], item["slots"]
                    if type not in self.types:
                        raise TypeError(f"unknown resource requirement type {type!r}")
                    r = self._get_from_pool(item["type"], item["slots"])
                    items = spec.setdefault(type, [])
                    items.append(r)
                    totals[type] = totals.get(type, 0) + slots
                resource_specs.append(spec)
        except Exception:
            self.unstash()
            raise
        else:
            self._stash = None
        if logging.LEVEL == logging.DEBUG:
            for type, n in totals.items():
                N = sum([_["slots"] for spec in self.pool for _ in spec[type]]) + n
                logging.debug(f"Acquiring {n} {type} from {N} available")
        obj.resources = resource_specs
        return

    def reclaim(self, obj: "AbstractTestCase") -> None:
        def _reclaim(type, rspec):
            pid, lid = self.local_ids(type, rspec["gid"])
            for spec in self.pool:
                if spec["id"] == pid:
                    for instance in spec[type]:
                        if instance["id"] == lid:
                            slots = rspec["slots"]
                            instance["slots"] += slots
                            return slots
            raise ValueError(f"Attempting to reclaim a resource whose ID is unknown: {rspec!r}")

        types: dict[str, int] = {}
        for resource in obj.resources:  # list[dict[str, list[dict]]]) -> None:
            for type, rspecs in resource.items():
                for rspec in rspecs:
                    n = _reclaim(type, rspec)
                    types[type] = types.setdefault(type, 0) + n
        for type, n in types.items():
            logging.debug(f"Reclaimed {n} {type}")
        obj.resources.clear()


class ResourceUnsatisfiable(Exception):
    pass


class ResourceUnavailable(Exception):
    pass
