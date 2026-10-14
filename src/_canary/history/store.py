# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import math
import os
import socket
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Protocol
from typing import Sequence

from .. import config
from ..util import json_helper as json
from ..util import logging
from ..util.filesystem import atomic_write
from ..util.filesystem import file_lock

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec
    from ..core.status import Status
    from ..core.timekeeper import Timekeeper

logger = logging.get_logger(__name__)

_cache_dir_logged: bool = False

SCHEMA = 1
KEEP = 50
MAX_BYTES = 32 * 1024


@dataclass
class RuntimeStatistics:
    count: int
    mean: float
    variance: float
    min: float
    max: float

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    @classmethod
    def from_durations(cls, durations: Sequence[float]) -> "RuntimeStatistics":
        n = len(durations)
        if n == 0:
            raise ValueError("No durations to compute runtime statistics")
        mean = statistics.mean(durations) if n > 1 else durations[0]
        variance = statistics.variance(durations) if n > 1 else 0.0
        return cls(count=n, mean=mean, variance=variance, min=min(durations), max=max(durations))


class StorableJob(Protocol):
    id: str

    @property
    def spec(self) -> "JobSpec": ...

    @property
    def timekeeper(self) -> "Timekeeper": ...

    @property
    def status(self) -> "Status": ...

    @property
    def timeout(self) -> float: ...


class RetrievableJob(Protocol):
    id: str

    @property
    def timeout(self) -> float: ...


class HistoryStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root

    @classmethod
    def open(cls, start: Path) -> "HistoryStore":
        root = _find_cache_dir(start=start)
        return cls(root)

    def path_for(self, job: "RetrievableJob") -> Path | None:
        if self.root is None:
            return None
        return self.root / "jobs" / job.id[:2] / f"{job.id[2:]}.jsonl"

    def load(self, job: "RetrievableJob") -> dict[str, Any] | None:
        if self.root is None:
            return None
        file = self.path_for(job)
        if file is None:
            return None
        if not file.exists():
            return None
        history: dict[str, Any] = {}
        lines = file.read_text()
        for line in lines.splitlines():
            if not line.strip():
                continue
            record = json.loads(line.strip())
            what = record.pop("what", None)
            if what == "meta":
                history["meta"] = record
            elif what == "record":
                history.setdefault("records", []).append(record)
        return history

    def record(self, job: "StorableJob") -> None:
        """Append one completion record for ``job``.  Never raises: the finish
        hook must not turn a history problem into a job failure."""
        if self.root is None:
            return
        try:
            self._record(job)
        except Exception:
            logger.debug("Failed to record history for %s", job.spec.id[:7], exc_info=True)

    def _record(self, job: "StorableJob") -> None:

        duration = float(job.timekeeper.running())
        if duration < 0:  # never started
            return
        run: dict[str, Any] = {
            "what": "record",
            "version": SCHEMA,
            "recorded_at": round(time.time(), 3),
            "status": job.status.outcome.name.lower(),
            "duration": round(duration, 3),
            "timeout": float(job.timeout),
            "timeout_multiplier": config.timeout_multiplier(),
            "file_hash": _content_hash(job),
            "host": socket.gethostname(),
        }
        path = self.path_for(job)
        assert path is not None
        path.parent.mkdir(parents=True, exist_ok=True)

        # One lock covers the compaction check and the append, so concurrent
        # workers and concurrent HPC batches sharing this cache cannot interleave.
        with file_lock(path):
            if not path.exists():
                self._append(path, _meta(job), run)
                return
            if path.stat().st_size > MAX_BYTES:
                self._compact(path, job)
            self._append(path, run)

    @staticmethod
    def _append(path: Path, *records: dict[str, Any]) -> None:
        with open(path, "a") as f:
            for rec in records:
                f.write(json.dumps(rec, default=str, separators=(",", ":")) + "\n")

    @staticmethod
    def _compact(path: Path, job: "StorableJob") -> None:

        meta: dict[str, Any] = {}
        runs: list[dict[str, Any]] = []
        for line in path.read_text().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:  # torn or corrupt line
                continue
            if rec.get("k") == "meta":
                meta = rec
            elif rec.get("k") == "run":
                runs.append(rec)

        totals = meta.get("totals", {})
        for r in runs[:-KEEP]:  # fold what we drop into lifetime counts
            totals[r["status"]] = totals.get(r["status"], 0) + 1
        meta = {**meta, **_meta(job), "totals": totals}  # refresh name, path, parameters

        out = [meta, *runs[-KEEP:]]
        atomic_write(
            path, "".join(json.dumps(r, default=str, separators=(",", ":")) + "\n" for r in out)
        )

    def runtime_statistics(self, job: "RetrievableJob") -> RuntimeStatistics | None:
        """Return the longest representative runtime recorded for ``job``, or ``None``.

        Uses ``max(mean, max)`` rather than the mean alone so that a few anomalously
        fast samples cannot drag the estimate down.
        """
        try:
            history = self.load(job)
        except Exception:
            logger.debug("Failed to load historic timing data for %s", job.id[:7], exc_info=True)
            return None
        if not history:
            return None
        durations = _durations(history.get("records", []))
        return RuntimeStatistics.from_durations(durations) if durations else None


def _find_cache_dir(start: Path | None = None) -> Path | None:
    """Return the job result cache directory, or None if none is configured.

    Resolution order:
    1. ``CANARY_CACHE_DIR`` environment variable
    2. ``run:cache:dir`` config key
    3. Walk up from *start* for a ``WORKSPACE.TAG`` anchor → ``<anchor>/cache``

    The resolved path (and its source) is logged at DEBUG level the first time
    this function returns a non-None result during the process lifetime, so
    operators can confirm which cache is in use without inspecting source code.
    """
    global _cache_dir_logged

    if "CANARY_CACHE_DIR" in os.environ:
        cache_dir = Path(os.environ["CANARY_CACHE_DIR"])
        if not _cache_dir_logged:
            logger.debug("Job cache dir (CANARY_CACHE_DIR): %s", cache_dir)
            _cache_dir_logged = True
        return cache_dir
    if raw := config.get("run:cache:dir"):
        cache_dir = Path(raw)
        if not _cache_dir_logged:
            logger.debug("Job cache dir (run:cache:dir config): %s", cache_dir)
            _cache_dir_logged = True
        return cache_dir
    d = start or Path.cwd()
    while d != d.parent:
        if (d / "WORKSPACE.TAG").exists():
            cache_dir = d / "cache"
            if not _cache_dir_logged:
                logger.debug("Job cache dir (WORKSPACE.TAG at %s): %s", d, cache_dir)
                _cache_dir_logged = True
            return cache_dir
        d = d.parent
    return None


def _content_hash(job: "StorableJob") -> str | None:
    from ..core.jobspec import _GlobalSpecCache

    path = job.spec.file_root / job.spec.file_path
    try:
        return _GlobalSpecCache.content_hash(path)
    except Exception:
        return None


def _meta(job: "StorableJob") -> dict[str, Any]:
    spec = job.spec
    return {
        "what": "meta",
        "version": SCHEMA,
        "id": spec.id,
        "name": spec.display_name(),
        "root": str(spec.file_root),
        "path": str(spec.file_path),
        "parameters": spec.parameters,
        "totals": {},
    }


def _durations(records: list[dict[str, Any]], *, status: str = "success") -> list[float]:
    return [
        float(r["duration"])
        for r in records
        if r.get("status") == status and r.get("duration") is not None
    ]
