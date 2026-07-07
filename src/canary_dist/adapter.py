# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import getpass
import json
import os
import subprocess
from collections import Counter
from typing import IO
from typing import Any
from urllib.parse import urlencode

import yaml

import canary
from _canary.resource_pool.rpool import Outcome
from _canary.resource_pool.rpool import ResourceUnavailable

logger = canary.get_logger(__name__)


class DistributedResourcePoolAdapter:
    """Client-side adapter for the distributed resource-pool server.

    The server stores resources per machine using its own flat resource schema.
    This adapter translates that state into canary-core's topology-aware
    resource-pool model.

    Checkout returns a canary-core allocation object:

        {
            "metadata": {
                "source": "distributed",
                "server_url": "...",
                "hostname": "...",
                "transaction_id": "...",
            },
            "resources": {
                "cpus": [
                    {"node": "host-a", "id": "0", "slots": 1}
                ]
            },
        }

    Checkin uses the allocation metadata to release the server-side transaction.
    """

    def __init__(self, *, server_url: str) -> None:
        if "://" not in server_url:
            server_url = f"http://{server_url}"

        self.server_url = server_url.rstrip("/")
        self.resource_counts: dict[str, dict[str, int]] = {}
        self.resource_types: list[str] = []
        self.update_resource_counts()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(server_url={self.server_url!r})"

    def update_resource_counts(self) -> None:
        """Update available resource counts from the server.

        Counts are filtered to the currently eligible distributed machines.
        Eligibility is handled here rather than in canary-core.
        """
        self.resource_counts.clear()
        self.resource_types.clear()

        data = self.current_state()
        db = data["database"]

        tags = canary.config.getoption("canary_dist_tags") or None
        groups = self._current_groups()

        rtypes: set[str] = {"cpus", "gpus"}

        for machine in db.get("machines", []):
            if not self._machine_eligible(machine, tags=tags, groups=groups):
                continue

            counts: dict[str, int] = self.resource_counts.setdefault(machine["hostname"], {})

            for rtype, instances in machine.get("resources", {}).items():
                counts[rtype] = sum(int(instance.get("slots", 0)) for instance in instances)
                rtypes.add(rtype)

        self.resource_types.extend(sorted(rtypes))

    def to_resource_pool(self) -> dict[str, Any]:
        """Translate server state into a canary-core ResourcePool spec.

        Distributed execution does not support multi-node submission, so
        ``allow_multinode`` is false. Each eligible machine becomes one Canary
        node with node-local resources.
        """
        data = self.current_state()
        db = data["database"]

        tags = canary.config.getoption("canary_dist_tags") or None
        groups = self._current_groups()

        nodes: list[dict[str, Any]] = []

        for machine in db.get("machines", []):
            if not self._machine_eligible(machine, tags=tags, groups=groups):
                continue

            resources = dict(machine.get("resources", {}))
            resources.setdefault("cpus", [])
            resources.setdefault("gpus", [])
            nodes.append(
                {
                    "id": machine["hostname"],
                    "resources": resources,
                    "additional_properties": {
                        "distributed": {
                            "state": machine.get("state", "online"),
                            "tags": machine.get("tags", []),
                            "groups": machine.get("groups", []),
                        }
                    },
                }
            )

        return {
            "allow_multinode": False,
            "additional_properties": {"source": "distributed", "server_url": self.server_url},
            "nodes": nodes,
        }

    def empty(self) -> bool:
        data = self.current_state()
        return not data["database"].get("machines")

    def dump(self, file: IO[Any]) -> None:
        data = self.current_state()
        yaml.dump(data, file, default_flow_style=False)

    def current_state(self) -> dict[str, Any]:
        p = self.curl("/status", method="GET")
        return self.parse_json_response(p)

    def max_count(self, type: str) -> int:
        return max((counts.get(type, 0) for counts in self.resource_counts.values()), default=0)

    def accommodates_remote(self, case: canary.TestCase) -> Outcome:
        """Ask the server whether a case can be accommodated."""
        p = self.curl("/accommodates", data={"resources": case.required_resources()})
        data = self.parse_json_response(p)
        return Outcome(data["accommodates"], reason=data["reason"])

    def accommodates(self, case: canary.TestCase) -> Outcome:
        """Determine locally whether an eligible machine can accommodate case.

        This is an approximation based on the resource counts read during
        adapter initialization. Actual checkout is server-authoritative.
        """
        required_resources = [
            member
            for member in case.required_resources()
            if member["type"] not in ("node", "nodes")
        ]

        for counts in self.resource_counts.values():
            slots_needed: Counter[str] = Counter()
            missing: set[str] = set()

            for member in required_resources:
                rtype = member["type"]

                if rtype not in counts:
                    missing.add(rtype)
                    break

                slots_needed[rtype] += int(member["slots"])

            if missing:
                continue

            wanting: set[str] = set()
            for rtype, slots in slots_needed.items():
                slots_avail = counts[rtype]
                if slots_avail < slots:
                    wanting.add(rtype)

            if wanting:
                continue

            return Outcome(True)

        return Outcome(False, reason="Resource requirements could not be accommodated")

    def checkout(self, request: list[dict[str, Any]], **kwds: Any) -> dict[str, Any]:
        """Checkout resources from the distributed server.

        Returns a canary-core allocation object:

            {
                "metadata": {...},
                "resources": {...}
            }
        """
        # Run the health check first to check in expired checkouts.
        self.curl("/rx")

        tags = canary.config.getoption("canary_dist_tags") or None
        groups = self._current_groups()
        timeout: float = kwds.get("timeout", 60.0 * 30.0)

        # The distributed server does not support multi-node submission.
        request_data = {
            "resources": [member for member in request if member["type"] not in ("node", "nodes")],
            "timeout": timeout,
            "tags": tags,
            "groups": groups,
        }

        p = self.curl("/checkout", data=request_data)
        data = self.parse_json_response(p)

        if not data["success"]:
            raise ResourceUnavailable(data["message"])

        hostname = data["hostname"]
        transaction_id = data["transaction_id"]
        resources = _with_node(data["resources"], hostname)

        return {
            "metadata": {
                "source": "distributed",
                "server_url": self.server_url,
                "hostname": hostname,
                "transaction_id": transaction_id,
            },
            "resources": resources,
        }

    def checkin(self, allocation: dict[str, Any]) -> None:
        """Release a server-side distributed resource allocation."""
        metadata = allocation.get("metadata", {})
        transaction_id = metadata.get("transaction_id")

        if not transaction_id:
            raise ValueError("Distributed allocation is missing metadata.transaction_id")

        p = self.curl("/checkin", data={"transaction_id": transaction_id})
        data = self.parse_json_response(p)

        if not data["success"]:
            logger.error(f"Failed to checkin resources for {transaction_id}")

    def curl(
        self, endpoint: str, method: str = "POST", data: Any = None, **parameters: str
    ) -> subprocess.CompletedProcess:
        url = f"{self.server_url}{endpoint}"

        if parameters:
            querystrings = urlencode(parameters)
            url += f"?{querystrings}"

        args = ["curl", "-s", "-g", "--fail-with-body"]
        args.extend(["-X", method])
        args.extend(["-H", f"X-User: {getpass.getuser()}"])
        args.extend(["-H", f"X-Host: {os.uname().nodename}"])
        args.append(url)

        if data is not None:
            args.extend(["-H", "Content-Type: application/json"])
            payload = json.dumps(data, separators=(",", ":"), indent=None)
            args.extend(["-d", payload])

        return subprocess.run(args, capture_output=True, text=True)

    def parse_json_response(self, p: subprocess.CompletedProcess) -> Any:
        if p.returncode != 0:
            message = (p.stderr or p.stdout or "").strip()
            if not message:
                message = f"curl failed with return code {p.returncode}"
            raise RuntimeError(message)

        try:
            return json.loads(p.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Server returned non-JSON response: {p.stdout!r}") from exc

    def _machine_eligible(
        self,
        machine: dict[str, Any],
        *,
        tags: list[str] | None = None,
        groups: list[str] | None = None,
    ) -> bool:
        if machine.get("state", "online") != "online":
            return False

        if tags and not all(tag in machine.get("tags", []) for tag in tags):
            return False

        if groups and not any(group in machine.get("groups", []) for group in groups):
            return False

        return True

    def _current_groups(self) -> list[str] | None:
        # FIXME: find and add the user's groups here, if/when desired.
        return None


def _with_node(
    resources: dict[str, list[dict[str, Any]]], node: str
) -> dict[str, list[dict[str, Any]]]:
    """Attach Canary node identity to flat server-side resource specs."""
    result: dict[str, list[dict[str, Any]]] = {}

    for rtype, rspecs in resources.items():
        result[rtype] = []

        for rspec in rspecs:
            item = dict(rspec)
            item["node"] = node
            result[rtype].append(item)

    return result
