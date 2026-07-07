# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import copy
import io
from typing import TYPE_CHECKING
from typing import Any

from .rpool import Outcome
from .rpool import ResourcePool
from .rpool import ResourceUnavailable
from .rpool import make_resource_pool

if TYPE_CHECKING:
    from ..config import Config as CanaryConfig
    from ..job import Job


class ResourceManager:
    """Owns the concrete resource pool for a Canary configuration.

    The parent process may discover resources through plugins.  Subprocesses
    should receive the resolved resource pool through the config snapshot and
    reconstruct it locally without rerunning discovery.
    """

    __slots__ = ("config", "_pool", "_snapshot_state")

    def __init__(self, config: "CanaryConfig") -> None:
        self.config = config
        self._pool: ResourcePool | None = None
        self._snapshot_state: dict[str, Any] | None = None

    def clear(self) -> None:
        self._pool = None
        self._snapshot_state = None

    invalidate = clear
    reset = clear

    def get_pool(self) -> ResourcePool:
        """Return the resource pool, constructing it lazily if needed."""
        if self._pool is not None:
            return self._pool

        if self._snapshot_state is not None:
            self._pool = ResourcePool(copy.deepcopy(self._snapshot_state))
            return self._pool

        self._pool = make_resource_pool(self.config)
        return self._pool

    def refresh(self) -> ResourcePool:
        """Force rediscovery/reconstruction of the resource pool.

        This should generally only be used in the parent process.
        """
        self.clear()
        return self.get_pool()

    def snapshot(self) -> dict[str, Any]:
        """Return resource-manager state suitable for a Config snapshot.

        This snapshots the resource pool as it exists at the time of snapshot.
        The returned state is plain JSON/YAML-compatible data.
        """
        pool = self.get_pool()
        return {"resource_pool": pool.getstate()}

    def load_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Load resource-manager state from a Config snapshot.

        After this, get_pool() reconstructs from the snapshot instead of running
        discovery hooks.
        """
        self._pool = None
        self._snapshot_state = None

        if pool_state := snapshot.get("resource_pool"):
            self._snapshot_state = copy.deepcopy(pool_state)

    def describe(self) -> str:
        file = io.StringIO()
        self.get_pool().dump(file)
        return file.getvalue()

    def types(self) -> list[str]:
        return self.get_pool().types

    def count(self, type: str) -> int:
        return self.get_pool().count(type)

    def count_per_node(self, type: str) -> int:
        try:
            return self.get_pool().count_per_node(type)
        except ResourceUnavailable:
            return 0

    def accommodates(self, case_or_request: "Job | list[dict[str, Any]]") -> Outcome:
        from ..job import Job

        request: list[dict[str, Any]]
        if isinstance(case_or_request, Job):
            request = case_or_request.required_resources()
        else:
            request = case_or_request
        return self.get_pool().accommodates(request)

    def checkout(self, request: list[dict[str, Any]], **kwds: Any) -> dict[str, dict]:
        return self.get_pool().checkout(request, **kwds)

    def checkin(self, allocation: dict[str, dict]) -> None:
        self.get_pool().checkin(allocation)
