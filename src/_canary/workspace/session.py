# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Session management for Canary test execution.

A Session represents a specific execution run of a set of jobs within a workspace.
"""

import dataclasses
import datetime
import sys
from pathlib import Path
from typing import Any

from .. import config
from ..core.job import Job
from ..core.job import Measurements
from ..util import json_helper as json


@dataclasses.dataclass
class Session:
    name: str
    jobs: list[Job]
    prefix: Path
    measurements: Measurements = dataclasses.field(default_factory=Measurements)
    job_ids: list[str] = dataclasses.field(default_factory=list)
    reused: bool = False  # True if this session reuses an existing session directory

    returncode: int = dataclasses.field(init=False, default=-1)
    #: Why the session stopped before its jobs finished (an exception canary raised), if it did.
    error: str | None = dataclasses.field(init=False, default=None)
    started_on: datetime.datetime = dataclasses.field(init=False, default=datetime.datetime.min)
    finished_on: datetime.datetime = dataclasses.field(init=False, default=datetime.datetime.min)

    def __post_init__(self) -> None:
        """Validates session jobs.

        Raises:
            ValueError: If any job in the session is unexpectedly masked.
        """
        if not self.job_ids:
            self.job_ids = [job.id for job in self.jobs]

        for job in self.jobs:
            if job.mask:
                raise ValueError(f"{job}: unexpectedly masked test job")

    @property
    def lockfile(self) -> Path:
        return self.prefix / "session.lock"

    def add_measurement(self, name: str, value: Any) -> None:
        """Add or update a session-level measurement.

        This mirrors the user/plugin-facing job measurement API. Session hooks
        can call this to record workflow, environment, scheduler, agent, or
        reporting metadata.
        """
        self.measurements.add_measurement(name, value)

    def to_lock_data(self) -> dict[str, Any]:
        """Return the session.lock manifest.

        This is intentionally a manifest, not a full Session serialization.
        Jobs are represented by ID only; authoritative job state lives in each
        testcase.lock and in the workspace database.
        """
        return {
            "name": self.name,
            "prefix": str(self.prefix),
            "root_at_creation": str(self.prefix.parent.parent.parent),
            "job_ids": [job.id for job in self.jobs],
            "returncode": self.returncode,
            "error": self.error,
            "started_on": self.started_on.isoformat(),
            "finished_on": self.finished_on.isoformat(),
            "argv": list(sys.argv),
            "config": config.snapshot(),
            "measurements": dict(self.measurements.data),
        }

    def save(self) -> None:
        """Write session.lock as plain JSON."""
        self.prefix.mkdir(parents=True, exist_ok=True)
        json.safesave(self.lockfile, self.to_lock_data(), indent=2)

    @staticmethod
    def load_lock_data(path: str | Path) -> dict[str, Any]:
        path = Path(path)
        lockfile = path / "session.lock" if path.is_dir() else path
        return json.loads(lockfile.read_text())

    @property
    def cases(self) -> list["Job"]:
        return self.jobs
