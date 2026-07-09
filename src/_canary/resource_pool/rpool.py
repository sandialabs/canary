# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import copy
import io
import math
import os
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

ResourceSpec = list[dict[str, Any]]
ResourceRequest = list[dict[str, Any]]
ResourceAllocation = dict[str, dict]


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


class AllocationTransaction:
    __slots__ = ("inventory", "deltas")

    def __init__(self, inventory: "Inventory") -> None:
        self.inventory = inventory
        self.deltas: list[tuple[str, str, int]] = []

    def record(self, rtype: str, rid: str, slots: int) -> None:
        self.deltas.append((rtype, rid, slots))

    def rollback(self) -> None:
        for rtype, rid, slots in self.deltas:
            for inst in self.inventory.resources[rtype]:
                if inst["id"] == rid:
                    inst["slots"] += slots
                    break

    def __enter__(self) -> "AllocationTransaction":
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.rollback()
        # propagate the exception
        return False


class Inventory:
    __slots__ = ("resources",)

    def __init__(self, resources: dict[str, ResourceSpec]) -> None:
        self.resources = resources

    def slots_available(self, rtype: str) -> int:
        return sum(int(inst["slots"]) for inst in self.resources.get(rtype, []))


class Allocator:
    def acquire(self, inventory: Inventory, rtype: str, slots: int) -> dict[str, Any]:
        instances = sorted(inventory.resources[rtype], key=lambda x: x["slots"])
        for instance in instances:
            if slots <= instance["slots"]:
                acquired = copy.deepcopy(instance)
                acquired["slots"] = slots
                instance["slots"] -= slots
                return acquired
        raise ResourceUnavailable


class Node:
    """Single-node resource inventory.

    This is essentially the old flat ResourcePool behavior, scoped to one node.
    Resource IDs are node-local.
    """

    __slots__ = ("id", "resources", "slots_per_resource_type", "additional_properties")

    def __init__(
        self,
        id: str,
        resources: dict[str, ResourceSpec] | None = None,
        *,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        self.id = str(id)
        self.resources: dict[str, ResourceSpec] = resources or {}
        self.slots_per_resource_type: Counter[str] = Counter()
        self.additional_properties = dict(additional_properties or {})
        self._recompute_slots()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id!r}>"

    def __contains__(self, rtype: str) -> bool:
        return rtype in self.resources

    @property
    def types(self) -> list[str]:
        return sorted(self.resources.keys())

    def empty(self) -> bool:
        return not self.resources

    def _recompute_slots(self) -> None:
        self.slots_per_resource_type.clear()
        for rtype, instances in self.resources.items():
            self.slots_per_resource_type[rtype] = sum(int(inst["slots"]) for inst in instances)

    def _resolve_type(self, rtype: str) -> str:
        if rtype in self.resources:
            return rtype
        plural = f"{rtype}s"
        if plural in self.resources:
            return plural
        raise ResourceUnavailable(rtype)

    def slots_available(self, rtype: str) -> int:
        rtype = self._resolve_type(rtype)
        return sum(int(inst["slots"]) for inst in self.resources.get(rtype, []))

    def count(self, rtype: str) -> int:
        rtype = self._resolve_type(rtype)
        return len(self.resources[rtype])

    def accommodates(self, request: ResourceRequest) -> Outcome:
        """Determine if this node can accommodate a per-node resource request."""
        slots_needed: Counter[str] = Counter()
        missing: set[str] = set()

        for member in request:
            rtype = member["type"]
            if rtype in ("node", "nodes"):
                continue
            try:
                rtype = self._resolve_type(rtype)
            except ResourceUnavailable:
                missing.add(rtype)
                continue
            slots_needed[rtype] += int(member["slots"])

        if missing:
            types = "[bold]%s[/]" % ",".join(sorted(missing))
            key = pluralize("Resource", n=len(missing))
            return Outcome(False, reason=f"{key} unavailable on node {self.id}: {types}")

        wanting: dict[str, tuple[int, int]] = {}
        for rtype, slots in slots_needed.items():
            slots_avail = self.slots_available(rtype)
            if slots_avail < slots:
                wanting[rtype] = (slots, slots_avail)

        if wanting:
            reason: str
            levelno: int = logging.get_level()
            if levelno <= logging.DEBUG:
                t = "[bold]%s[/] (requested %d, available %d)"
                types = ", ".join(t % (k, *wanting[k]) for k in sorted(wanting))
                reason = f"insufficient slots on node {self.id} of {types}"
            else:
                types = ", ".join("[bold]%s[/]" % t for t in wanting)
                reason = f"insufficient slots on node {self.id} of {types}"
            return Outcome(False, reason=reason)

        return Outcome(True)

    def score(self, request: ResourceRequest) -> float:
        """Score this node after satisfying request.

        Higher score means more residual capacity. This borrows the idea from
        dpool.py, but computes the score without mutating the node.
        """
        if not self.accommodates(request):
            return -1.0

        slots_needed: Counter[str] = Counter()
        for member in request:
            rtype = member["type"]
            if rtype in ("node", "nodes"):
                continue
            rtype = self._resolve_type(rtype)
            slots_needed[rtype] += int(member["slots"])

        score = 0.0
        for rtype, slots in slots_needed.items():
            slots_free = self.slots_available(rtype)
            diff = max(0, slots_free - slots)
            score += diff**2
        return math.sqrt(score)

    def checkout(self, request: ResourceRequest) -> dict[str, list[dict]]:
        """Check resources out of this node.

        Returned resource specs include the node ID.
        """
        acquired: dict[str, list[dict]] = {}
        inventory = Inventory(self.resources)
        allocator = Allocator()

        with AllocationTransaction(inventory) as transaction:
            for item in request:
                rtype, slots = item["type"], int(item["slots"])
                if rtype in ("node", "nodes"):
                    continue

                rtype = self._resolve_type(rtype)
                rspec = allocator.acquire(inventory, rtype, slots)
                rspec["node"] = self.id

                acquired.setdefault(rtype, []).append(rspec)
                transaction.record(rtype, rspec["id"], slots)

        self._recompute_slots()
        return acquired

    def checkin(self, resources: dict[str, list[dict]]) -> None:
        for rtype, rspecs in resources.items():
            rtype = self._resolve_type(rtype)
            for rspec in rspecs:
                for inst in self.resources[rtype]:
                    if inst["id"] == rspec["id"]:
                        inst["slots"] += int(rspec["slots"])
                        break
                else:
                    raise ValueError(
                        f"Attempting to checkin a resource with unknown ID on node "
                        f"{self.id}: {rspec!r}"
                    )
        self._recompute_slots()

    def pop(self, rtype: str) -> ResourceSpec | None:
        if rtype in self.resources:
            del self.slots_per_resource_type[rtype]
            return self.resources.pop(rtype)
        return None

    def getstate(self) -> dict[str, Any]:
        state: dict[str, Any] = {"id": self.id, "resources": copy.deepcopy(self.resources)}
        if self.additional_properties:
            state["additional_properties"] = copy.deepcopy(self.additional_properties)
        return state

    def has_resource(self, rtype: str) -> bool:
        if rtype in self.resources:
            return True
        if f"{rtype}s" in self.resources:
            return True
        return False

    def get_resource(self, rtype: str, default: ResourceSpec | None = None) -> ResourceSpec | None:
        try:
            rtype = self._resolve_type(rtype)
        except ResourceUnavailable:
            return default
        return self.resources.get(rtype, default)

    def set_resource(self, rtype: str, specs: ResourceSpec) -> None:
        self.resources[rtype] = copy.deepcopy(specs)
        self._recompute_slots()

    def set_resources(self, resources: dict[str, ResourceSpec]) -> None:
        self.resources = copy.deepcopy(resources)
        self._recompute_slots()

    def set_resource_count(self, rtype: str, count: int) -> None:
        self.resources[rtype] = [{"id": str(j), "slots": 1} for j in range(count)]
        self._recompute_slots()

    def set_slots_per_resource(self, rtype: str, slots: int) -> None:
        rtype = self._resolve_type(rtype)
        for instance in self.resources[rtype]:
            instance["slots"] = slots
        self._recompute_slots()

    def multiply_slots_per_resource(self, rtype: str, factor: int) -> None:
        rtype = self._resolve_type(rtype)
        for instance in self.resources[rtype]:
            instance["slots"] *= factor
        self._recompute_slots()


class ResourcePool:
    """Topology-aware resource pool.

    Canonical resource-pool layout:

    .. code-block:: yaml

        resource_pool:
          allow_multinode: true
          additional_properties: {}
          nodes:
          - id: node-0
            resources:
              cpus:
              - id: "0"
                slots: 1
              gpus:
              - id: "0"
                slots: 1

    Resource IDs are node-local. Checked-out resources include the owning node:

    .. code-block:: python

        {
            "gpus": [
                {"node": "node-0", "id": "0", "slots": 1}
            ]
        }

    Multi-node semantics:

    - Without an explicit ``nodes`` request, checkout is single-node.
    - With ``{"type": "nodes", "slots": N}``, the remaining resource request
      is interpreted as per-node.
    """

    __slots__ = ("additional_properties", "nodes", "_node_index", "_allow_multinode")

    def __init__(self, pool: dict[str, Any] | None = None, allow_multinode: bool = True) -> None:
        self.additional_properties: dict[str, Any] = {}
        self.nodes: list[Node] = []
        self._node_index: dict[str, Node] = {}
        self._allow_multinode = allow_multinode
        if pool:
            self.fill(pool)

    def __repr__(self) -> str:
        file = io.StringIO()
        self.dump(file)
        return file.getvalue()

    def __contains__(self, rtype: str) -> bool:
        if rtype in ("node", "nodes"):
            return True
        return any(rtype in node.resources for node in self.nodes)

    @property
    def types(self) -> list[str]:
        types: set[str] = set()
        for node in self.nodes:
            types.update(node.types)
        return sorted(types)

    @property
    def resources(self) -> dict[str, ResourceSpec]:
        """Aggregate view of resources across all nodes.

        This is primarily a convenience view. Resource specs in this aggregate
        include the owning node ID.
        """
        resources: dict[str, ResourceSpec] = {}
        for node in self.nodes:
            for rtype, instances in node.resources.items():
                for instance in instances:
                    item = copy.deepcopy(instance)
                    item["node"] = node.id
                    resources.setdefault(rtype, []).append(item)
        return resources

    @property
    def slots_per_resource_type(self) -> Counter[str]:
        slots: Counter[str] = Counter()
        for node in self.nodes:
            slots.update(node.slots_per_resource_type)
        return slots

    def empty(self) -> bool:
        return len(self.nodes) == 0

    def clear(self) -> None:
        self.additional_properties.clear()
        self.nodes.clear()
        self._node_index.clear()

    def dump(self, file: IO[Any]) -> None:
        pool = self.getstate()
        yaml.dump({"resource_pool": pool}, file, default_flow_style=False)

    def getstate(self) -> dict[str, Any]:
        return {
            "additional_properties": copy.deepcopy(self.additional_properties),
            "nodes": [node.getstate() for node in self.nodes],
        }

    def fill(self, pool: dict[str, Any]) -> None:
        pool = resource_pool_schema.validate(pool)
        self.clear()

        self.additional_properties.update(pool.get("additional_properties", {}))

        for node_spec in pool["nodes"]:
            node = Node(
                id=str(node_spec["id"]),
                resources=copy.deepcopy(node_spec.get("resources", {})),
                additional_properties=node_spec.get("additional_properties", {}),
            )
            if node.id in self._node_index:
                raise ValueError(f"Duplicate node ID in resource pool: {node.id!r}")
            self.nodes.append(node)
            self._node_index[node.id] = node

    def populate(self, **kwds: int) -> None:
        if "cpus" not in kwds:
            kwds["cpus"] = cpu_count()
        if "gpus" not in kwds:
            kwds["gpus"] = 0

        resources: dict[str, ResourceSpec] = {}
        for rtype, count in kwds.items():
            resources[rtype] = [{"id": str(j), "slots": 1} for j in range(count)]

        pool = {
            "additional_properties": {},
            "nodes": [{"id": os.uname().nodename, "resources": resources}],
        }
        self.fill(pool)

    def node_ids(self) -> list[str]:
        return [node.id for node in self.nodes]

    def get_node(self, node_id: str) -> Node:
        try:
            return self._node_index[str(node_id)]
        except KeyError:
            raise ResourceUnavailable(f"Unknown node {node_id!r}") from None

    def get_property(self, name: str) -> Any:
        return self.additional_properties.get(name)

    def _resolve_type(self, rtype: str) -> str:
        if rtype in ("node", "nodes"):
            return "nodes"

        if any(rtype in node.resources for node in self.nodes):
            return rtype

        plural = f"{rtype}s"
        if any(plural in node.resources for node in self.nodes):
            return plural

        raise ResourceUnavailable(rtype)

    def count(self, rtype: str) -> int:
        if rtype in ("node", "nodes"):
            return len(self.nodes)

        rtype = self._resolve_type(rtype)
        return sum(len(node.resources.get(rtype, [])) for node in self.nodes)

    def count_by_node(self, rtype: str) -> dict[str, int]:
        rtype = self._resolve_type(rtype)
        if rtype == "nodes":
            return {node.id: 1 for node in self.nodes}
        return {node.id: len(node.resources.get(rtype, [])) for node in self.nodes}

    def slots_available(self, rtype: str) -> int:
        rtype = self._resolve_type(rtype)
        if rtype == "nodes":
            return len(self.nodes)
        return sum(node.slots_available(rtype) for node in self.nodes if rtype in node.resources)

    def slots_by_node(self, rtype: str) -> dict[str, int]:
        rtype = self._resolve_type(rtype)
        if rtype == "nodes":
            return {node.id: 1 for node in self.nodes}
        return {
            node.id: node.slots_available(rtype) if rtype in node.resources else 0
            for node in self.nodes
        }

    def count_per_node(self, rtype: str) -> int:
        counts = self.count_by_node(rtype)
        values = set(counts.values())

        if len(values) == 1:
            return values.pop()

        details = ", ".join(f"{node}:{count}" for node, count in sorted(counts.items()))
        raise ResourceUnavailable(f"Resource {rtype!r} is not homogeneous across nodes: {details}")

    def pop(self, rtype: str) -> ResourceSpec | None:
        popped: ResourceSpec = []
        for node in self.nodes:
            rspec = node.pop(rtype)
            if rspec:
                for item in rspec:
                    item = copy.deepcopy(item)
                    item["node"] = node.id
                    popped.append(item)
        return popped or None

    def _split_node_request(self, request: ResourceRequest) -> tuple[int, ResourceRequest]:
        nodes_requested: int | None = None
        resource_request: list[dict[str, Any]] = []

        for item in request:
            rtype = item["type"]
            if rtype in ("node", "nodes"):
                nodes_requested = int(item["slots"])
            else:
                resource_request.append(item)

        return nodes_requested or 1, resource_request

    def accommodates(self, request: ResourceRequest) -> Outcome:
        """Determine if the resources for this test are available."""
        if self.empty():
            raise EmptyResourcePoolError

        nodes_requested, per_node_request = self._split_node_request(request)

        if nodes_requested <= 1:
            reasons: list[str] = []
            for node in self.nodes:
                outcome = node.accommodates(per_node_request)
                if outcome:
                    return Outcome(True)
                if outcome.reason:
                    reasons.append(outcome.reason)
            reason = "No single node can accommodate requested resources"
            if logging.get_level() <= logging.DEBUG and reasons:
                reason += ": " + "; ".join(reasons)
            return Outcome(False, reason=reason)

        if not self.allow_multinode:
            return Outcome(
                False,
                reason="Multi-node allocation requested but this resource pool does not allow it",
            )

        candidates = [node for node in self.nodes if node.accommodates(per_node_request)]
        if len(candidates) < nodes_requested:
            return Outcome(
                False,
                reason=(
                    f"Requested {nodes_requested} nodes, but only {len(candidates)} "
                    "can accommodate the per-node resource request"
                ),
            )

        return Outcome(True)

    def checkout(self, request: ResourceRequest, **kwds: Any) -> ResourceAllocation:
        """Returns resources available to the test.

        Returned resources have the form:

        .. code-block:: python

            {
                "metadata": {},
                "resources": {
                    "<type>": [
                        {"node": "<node-id>", "id": "<local-resource-id>", "slots": N},
                        ...
                    ],
                    ...
                }
            }

        For multi-node checkout, ``nodes=N`` means the non-node resource request
        is applied independently to each selected node.
        """
        if self.empty():
            raise EmptyResourcePoolError
        nodes_requested, per_node_request = self._split_node_request(request)
        if nodes_requested <= 1:
            return self._checkout_single_node(per_node_request)
        return self._checkout_multi_node(nodes_requested, per_node_request)

    def _checkout_single_node(self, request: ResourceRequest) -> ResourceAllocation:
        candidates = [node for node in self.nodes if node.accommodates(request)]

        if not candidates:
            raise ResourceUnavailable("No single node can accommodate requested resources")

        # Prefer the node with the most residual capacity after the checkout.
        node = max(candidates, key=lambda candidate: candidate.score(request))
        acquired = node.checkout(request)

        self._log_acquired(acquired)
        return {"metadata": {}, "resources": acquired}

    def _checkout_multi_node(
        self, nodes_requested: int, request: ResourceRequest
    ) -> ResourceAllocation:
        if not self.allow_multinode:
            raise ResourceUnavailable(
                "Multi-node allocation requested but this resource pool does not allow it"
            )

        candidates = [node for node in self.nodes if node.accommodates(request)]
        candidates.sort(key=lambda node: node.score(request), reverse=True)
        selected = candidates[:nodes_requested]
        if len(selected) < nodes_requested:
            raise ResourceUnavailable(
                f"Requested {nodes_requested} nodes, but only {len(selected)} "
                "can accommodate the per-node resource request"
            )

        acquired: dict[str, list[dict]] = {}
        checked_out_nodes: list[tuple[Node, dict[str, list[dict]]]] = []

        try:
            for node in selected:
                node_acquired = node.checkout(request)
                checked_out_nodes.append((node, node_acquired))
                for rtype, rspecs in node_acquired.items():
                    acquired.setdefault(rtype, []).extend(rspecs)
        except Exception:
            for node, node_acquired in checked_out_nodes:
                node.checkin(node_acquired)
            raise

        self._log_acquired(acquired)
        return {"metadata": {}, "resources": acquired}

    def checkin(self, allocation: ResourceAllocation) -> None:
        checked_in: Counter[str] = Counter()

        for rtype, rspecs in allocation["resources"].items():
            by_node: dict[str, list[dict]] = {}
            for rspec in rspecs:
                if "node" not in rspec:
                    raise ValueError(f"Checked-in resource is missing node field: {rspec!r}")
                node_id = str(rspec["node"])
                by_node.setdefault(node_id, []).append(rspec)

            for node_id, node_rspecs in by_node.items():
                try:
                    node = self._node_index[node_id]
                except KeyError:
                    raise ValueError(
                        f"Attempting to checkin resource for unknown node {node_id!r}"
                    ) from None
                node.checkin({rtype: node_rspecs})
                checked_in[rtype] += sum(int(rspec["slots"]) for rspec in node_rspecs)

        if logging.get_level() <= logging.DEBUG:
            for rtype, n in checked_in.items():
                key = rtype[:-1] if n == 1 and rtype.endswith("s") else rtype
                logger.debug(f"Checked in {n} {key}")

    def _log_acquired(self, acquired: dict[str, list[dict]]) -> None:
        if logging.get_level() > logging.DEBUG:
            return

        totals: Counter[str] = Counter()
        for rtype, rspecs in acquired.items():
            totals[rtype] = sum(int(rspec["slots"]) for rspec in rspecs)

        for rtype, n in totals.items():
            key = rtype[:-1] if n == 1 and rtype.endswith("s") else rtype
            logger.debug(f"Acquiring {n} {key}")

    def first_node(self) -> Node:
        if not self.nodes:
            raise EmptyResourcePoolError
        return self.nodes[0]

    def ensure_node(self, node_id: str | None = None) -> Node:
        if node_id is None:
            if self.nodes:
                return self.nodes[0]
            node_id = os.uname().nodename

        node_id = str(node_id)

        if node_id in self._node_index:
            return self._node_index[node_id]

        node = Node(id=node_id, resources={})
        self.nodes.append(node)
        self._node_index[node.id] = node
        return node

    def add_node(self, node: Node) -> None:
        if node.id in self._node_index:
            raise ValueError(f"Duplicate node ID in resource pool: {node.id!r}")
        self.nodes.append(node)
        self._node_index[node.id] = node

    def rebuild_node_index(self) -> None:
        self._node_index.clear()
        for node in self.nodes:
            if node.id in self._node_index:
                raise ValueError(f"Duplicate node ID in resource pool: {node.id!r}")
            self._node_index[node.id] = node

    @property
    def allow_multinode(self) -> bool:
        return self._allow_multinode

    @allow_multinode.setter
    def allow_multinode(self, arg: bool) -> None:
        self._allow_multinode = bool(arg)

    def set_resource_count(self, rtype: str, count: int, *, node_id: str | None = None) -> None:
        if node_id is not None:
            self.get_node(node_id).set_resource_count(rtype, count)
            return

        for node in self.nodes:
            node.set_resource_count(rtype, count)

    def set_slots_per_resource(self, rtype: str, slots: int, *, node_id: str | None = None) -> None:
        if node_id is not None:
            self.get_node(node_id).set_slots_per_resource(rtype, slots)
            return

        for node in self.nodes:
            if node.has_resource(rtype):
                node.set_slots_per_resource(rtype, slots)

    def multiply_slots_per_resource(
        self, rtype: str, factor: int, *, node_id: str | None = None
    ) -> None:
        if node_id is not None:
            self.get_node(node_id).multiply_slots_per_resource(rtype, factor)
            return

        for node in self.nodes:
            if node.has_resource(rtype):
                node.multiply_slots_per_resource(rtype, factor)


def make_resource_pool(config: "CanaryConfig") -> ResourcePool:
    data = config.pluginmanager.hook.canary_resource_pool_fill(config=config)
    if data is None:
        raise EmptyResourcePoolError("No resource pool was created")
    allow_multinode: bool = data.pop("allow_multinode", True)
    data = resource_pool_schema.validate(data)
    pool = ResourcePool(data, allow_multinode=allow_multinode)
    config.pluginmanager.hook.canary_resource_pool_update(config=config, pool=pool)
    return pool


class ResourceUnavailable(Exception):
    pass


class EmptyResourcePoolError(Exception):
    pass
