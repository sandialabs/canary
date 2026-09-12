# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import copy
from collections import Counter
from dataclasses import dataclass
from typing import Any


class ResourceUnavailable(Exception):
    pass


class EmptyResourcePoolError(Exception):
    pass


@dataclass(slots=True)
class Outcome:
    ok: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.ok and not self.reason:
            raise ValueError(f"{self.__class__.__name__}(False) requires a reason")

    def __bool__(self) -> bool:
        return self.ok


class ResourcePool:
    """
    Minimal server-side resource pool.

    Resource format:

        {
            "cpus": [
                {"id": "0", "slots": 1},
                {"id": "1", "slots": 1}
            ],
            "gpus": [
                {"id": "0", "slots": 1}
            ]
        }

    Checkout request format:

        [
            {"type": "cpus", "slots": 1},
            {"type": "gpus", "slots": 1}
        ]

    Checkout response format:

        {
            "cpus": [
                {"id": "0", "slots": 1}
            ],
            "gpus": [
                {"id": "0", "slots": 1}
            ]
        }
    """

    def __init__(self, resources: dict[str, list[dict[str, Any]]] | None = None) -> None:
        # Deep copy is intentional. The distributed pool does trial allocations
        # while choosing the best machine. Trial allocations must not mutate the
        # database until the selected machine is committed.
        self.resources: dict[str, list[dict[str, Any]]] = copy.deepcopy(resources or {})

    def empty(self) -> bool:
        return not self.resources

    @property
    def types(self) -> list[str]:
        return sorted(self.resources)

    def count(self, rtype: str) -> int:
        return len(self.resources.get(rtype, []))

    def slots_available(self, rtype: str) -> int:
        return sum(int(instance.get("slots", 0)) for instance in self.resources.get(rtype, []))

    def accommodates(self, request: list[dict[str, Any]]) -> Outcome:
        if self.empty():
            return Outcome(False, reason="Resource pool is empty")

        slots_needed: Counter[str] = Counter()

        for item in request:
            rtype = item["type"]
            slots = int(item["slots"])

            if rtype not in self.resources:
                return Outcome(False, reason=f"Resource unavailable: {rtype}")

            slots_needed[rtype] += slots

        for rtype, needed in slots_needed.items():
            available = self.slots_available(rtype)
            if available < needed:
                return Outcome(
                    False,
                    reason=(
                        f"Insufficient slots of {rtype}: requested {needed}, available {available}"
                    ),
                )

        return Outcome(True)

    def checkout(self, request: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        if self.empty():
            raise EmptyResourcePoolError("Resource pool is empty")

        original = copy.deepcopy(self.resources)
        acquired: dict[str, list[dict[str, Any]]] = {}

        try:
            for item in request:
                rtype = item["type"]
                slots = int(item["slots"])

                if slots <= 0:
                    raise ResourceUnavailable(f"Invalid slot request for {rtype}: {slots}")

                if rtype not in self.resources:
                    raise ResourceUnavailable(f"Unknown resource type: {rtype}")

                rspec = self._acquire_one(rtype, slots)
                acquired.setdefault(rtype, []).append(rspec)

        except Exception:
            self.resources = original
            raise

        return acquired

    def _acquire_one(self, rtype: str, slots: int) -> dict[str, Any]:
        # Prefer the smallest resource instance that can satisfy the request.
        instances = sorted(self.resources[rtype], key=lambda instance: int(instance["slots"]))

        for instance in instances:
            available = int(instance.get("slots", 0))
            if available >= slots:
                instance["slots"] = available - slots
                return {"id": instance["id"], "slots": slots}

        raise ResourceUnavailable(f"Insufficient slots of {rtype}")

    def checkin(self, resources: dict[str, list[dict[str, Any]]]) -> None:
        for rtype, rspecs in resources.items():
            if rtype not in self.resources:
                raise ValueError(f"Attempting to check in unknown resource type: {rtype}")

            by_id = {instance["id"]: instance for instance in self.resources[rtype]}

            for rspec in rspecs:
                rid = rspec["id"]
                slots = int(rspec["slots"])

                if rid not in by_id:
                    raise ValueError(f"Attempting to check in resource with unknown ID: {rspec!r}")

                by_id[rid]["slots"] = int(by_id[rid].get("slots", 0)) + slots
