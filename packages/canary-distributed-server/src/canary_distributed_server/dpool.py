# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import json
import logging
import math
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import IO
from typing import Any
from typing import cast

import yaml
from schema import SchemaError

from .rpool import Outcome
from .rpool import ResourcePool
from .rpool import ResourceUnavailable
from .schemas import machinefile_schema

logger = logging.getLogger(__name__)


class MachineResourcePool(ResourcePool):
    def __init__(self, resources: dict[str, Any]) -> None:
        super().__init__(resources=resources)

    def score(self, groups: dict[str, list[dict]]) -> float:
        acquired: Counter[str] = Counter()
        for rtype, rspec in groups.items():
            acquired[rtype] += sum(ispec["slots"] for ispec in rspec)
        score: float = 0.0
        for rtype, slots_checked_out in acquired.items():
            slots_free = sum(instance["slots"] for instance in self.resources[rtype])
            diff = max(0, slots_free - slots_checked_out)
            score += diff**2
        return math.sqrt(score)


class DistributedResourcePool:
    def __init__(self, machinefile: str | Path) -> None:
        self.file = Path(machinefile)
        self.db: dict[str, Any]
        if not self.file.exists():
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.db = {"machines": []}
            self.save()
        else:
            self.db = self.load()
        self.resource_counts: dict[str, dict[str, int]] = {}
        rtypes: set[str] = {"cpus", "gpus"}
        for machine in self.db["machines"]:
            hostname: str = cast(str, machine["hostname"])
            counts: dict[str, int] = self.resource_counts.setdefault(hostname, {})
            for rtype, instances in machine["resources"].items():
                counts[rtype] = len(instances)
                rtypes.add(rtype)
        self.resource_types = sorted(rtypes)

    def empty(self) -> bool:
        return not self.db.get("machines")

    def dump(self, file: IO[Any]) -> None:
        yaml.dump(self.db, file, default_flow_style=False)

    def load(self) -> dict[str, Any]:
        db: dict[str, Any] = {}
        try:
            with open(self.file) as fh:
                db.update(json.load(fh))
        except FileNotFoundError:
            db["machines"] = []
        db.setdefault("machines", [])
        if db["machines"]:
            try:
                machinefile_schema.validate(db)
            except SchemaError as exc:
                raise ValueError(str(exc)) from exc
        counts: Counter[str] = Counter()
        for machine in db["machines"]:
            counts[machine["hostname"]] += 1
        errors = 0
        for host, count in counts.items():
            if count > 1:
                errors += 1
                logger.error(f"duplicate host {host} in {self.file}")
        if errors:
            raise ValueError("Stopping due to previous errors")
        return db

    def save(self) -> None:
        tmp = self.file.with_suffix(".tmp")
        with open(tmp, "w") as fh:
            json.dump(self.db, fh, indent=2)
            fh.flush()
        tmp.replace(self.file)

    def add(
        self,
        host: str,
        resources: list[dict[str, Any]],
        tags: list[str] | None = None,
        groups: list[str] | None = None,
        state: str | None = None,
    ) -> None:
        counts: Counter[str] = Counter()
        for resource in resources:
            counts[resource["type"]] = resource["count"]
        if "cpus" not in counts:
            raise ValueError("must add cpus")
        new_machine: dict[str, Any] = {"hostname": host, "state": state or "online"}
        if tags:
            new_machine["tags"] = tags
        if groups:
            new_machine["groups"] = groups
        for type, count in counts.items():
            rspec = [{"id": str(j), "slots": 1} for j in range(count)]
            new_machine.setdefault("resources", {}).update({type: rspec})
        for machine in self.db["machines"]:
            if machine["hostname"] == new_machine["hostname"]:
                raise ValueError(f"Host {machine['hostname']} is already in {self.file}")
        self.db["machines"].append(new_machine)

    def pop(self, host: str) -> None:
        original_count = len(self.db["machines"])
        machines = [m for m in self.db["machines"] if m["hostname"] != host]
        if len(machines) == original_count:
            raise ValueError(f"Could not find machine {host}")
        self.db["machines"].clear()
        self.db["machines"].extend(machines)

    def reset(self) -> None:
        for machine in self.db["machines"]:
            for rspec in machine["resources"].values():
                for ispec in rspec:
                    ispec["slots"] = 1

    def max_count(self, type: str) -> int:
        return max([counts.get(type, 0) for counts in self.resource_counts.values()], default=0)

    def accommodates(self, request: list[dict[str, Any]]) -> Outcome:
        """Determine if any online machine currently has enough free slots for ``request``.

        Uses the live pool state (current slot counts after checkouts), not the initial
        resource counts. Offline and maintenance machines are excluded.
        """
        for machine in self.db["machines"]:
            # Only consider online machines
            if machine.get("state", "online") != "online":
                continue

            pool = MachineResourcePool(machine["resources"])
            result = pool.accommodates(request)
            if result:
                return Outcome(True)

        return Outcome(False, reason="Resource requirements could not be accommodated")

    def checkout(
        self,
        request: list[dict[str, Any]],
        tags: list[str] | None = None,
        groups: list[str] | None = None,
    ) -> tuple[str, dict[str, list[dict]]]:
        slots_needed: Counter[str] = Counter()
        for member in request:
            slots_needed[member["type"]] += member["slots"]

        pools: dict[str, MachineResourcePool] = {}
        best = SimpleNamespace(host=None, acquired=None)
        best_score: float = -1.0
        machine: dict[str, Any]
        for machine in self.db["machines"]:
            # Skip offline/maintenance machines
            if machine.get("state", "online") != "online":
                continue
            if tags and not all(tag in machine.get("tags", []) for tag in tags):
                continue
            if groups and not any(group in machine.get("groups", []) for group in groups):
                continue
            host = machine["hostname"]
            pool = pools[host] = MachineResourcePool(machine["resources"])
            try:
                acquired = pool.checkout(request)
            except Exception:
                continue
            else:
                score = pool.score(acquired)
                if score > best_score:
                    best_score = score
                    best = SimpleNamespace(host=host, acquired=acquired)
        if not best.host:
            raise ResourceUnavailable
        for machine in self.db["machines"]:
            if machine["hostname"] == best.host:
                machine["resources"].clear()
                machine["resources"].update(pools[best.host].resources)
        return (best.host, best.acquired)

    def checkin(self, hostname: str, resources: dict[str, list[dict]]) -> None:
        """
        Release previously reserved resources. Busy counts never go below zero.
        """
        for machine in self.db["machines"]:
            if machine["hostname"] == hostname:
                pool = MachineResourcePool(machine["resources"])
                pool.checkin(resources)
                machine["resources"].clear()
                machine["resources"].update(pool.resources)
                break
        else:
            raise ValueError("Could not find machine")

    def take_offline(self, hostname: str) -> None:
        for machine in self.db["machines"]:
            if machine["hostname"] == hostname:
                machine["state"] = "offline"
                break
        else:
            raise ValueError("Could not find machine")

    def bring_online(self, hostname: str) -> None:
        for machine in self.db["machines"]:
            if machine["hostname"] == hostname:
                machine["state"] = "online"
                break
        else:
            raise ValueError("Could not find machine")
