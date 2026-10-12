# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Protocol

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


@dataclass
class RuntimeStatistics:
    mean: float
    min: float
    max: float
    variance: float
    count: int


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
        """Return the path to the per-job timing cache file, or None if absent."""
        if self.root is None:
            return None
        cache_file = self.root / "jobs" / job.id[:2] / f"{job.id[2:]}.json"
        return cache_file

    def load(self, job: "RetrievableJob") -> dict[str, Any] | None:
        if self.root is None:
            return None
        if (file := self.path_for(job)) and file.exists():
            return json.loads(file.read_text())["cache"]
        return None

    def record(self, job: "StorableJob") -> None:
        """store relevant information for this run"""
        from ..core.jobspec import _GlobalSpecCache

        if self.root is None:
            return None

        if not job.status.is_success():
            return

        file = self.path_for(job)
        assert file is not None
        file.parent.mkdir(parents=True, exist_ok=True)
        # Lock the individual cache file for the whole read-modify-write so
        # concurrent workers and concurrent HPC batches sharing this cache do
        # not lose one another's updates.
        with file_lock(file):
            cache: dict[str, Any]
            if not file.exists():
                cache = {
                    ".version": [3, 0],
                    "meta": {
                        "name": job.spec.display_name(),
                        "id": job.spec.id,
                        "root": job.spec.file_root,
                        "path": job.spec.file_path,
                        "parameters": job.spec.parameters,
                    },
                }
            else:
                cache = json.loads(file.read_text())["cache"]
            # Record the current file content hash so consumers can detect
            # that a test was edited since these metrics were recorded (the
            # id itself is content-independent).
            try:
                meta = cache.setdefault("meta", {})
                meta["content_hash"] = _GlobalSpecCache.content_hash(
                    job.spec.file_root / job.spec.file_path
                )
            except Exception:
                logger.debug("Failed to record content hash", exc_info=True)
            history = cache.setdefault("history", {})
            fn = datetime.datetime.fromtimestamp
            dt = fn(job.timekeeper._started) if job.timekeeper._started > 0 else None
            if dt is not None:
                history["last_run"] = dt.strftime("%c")
            name = job.status.category.lower()
            history[name] = history.get(name, 0) + 1
            if job.timekeeper.running() >= 0 and job.status.is_success():
                count: int = 0
                metrics = cache.setdefault("metrics", {})
                t = metrics.setdefault("time", {})
                if t:
                    # Welford's single pass online algorithm to update statistics
                    count, mean, variance = t["count"], t["mean"], t["variance"]
                    delta = job.timekeeper.running() - mean
                    mean += delta / (count + 1)
                    M2 = variance * count
                    delta2 = job.timekeeper.running() - mean
                    M2 += delta * delta2
                    variance = M2 / (count + 1)
                    minimum = min(t["min"], job.timekeeper.running())
                    maximum = max(t["max"], job.timekeeper.running())
                else:
                    variance = 0.0
                    mean = minimum = maximum = job.timekeeper.running()
                t["mean"] = mean
                t["min"] = minimum
                t["max"] = maximum
                t["variance"] = variance
                t["count"] = count + 1
            atomic_write(file, json.dumps({"cache": cache}, indent=2))

    def runtime_statistics(self, job: "RetrievableJob") -> RuntimeStatistics | None:
        """Return the longest representative runtime recorded for ``job``, or ``None``.

        Uses ``max(mean, max)`` rather than the mean alone so that a few anomalously
        fast samples cannot drag the estimate down.
        """

        cache = self.load(job)
        try:
            cache = self.load(job)
        except Exception:
            logger.debug("Failed to load historic timing data for %s", job.id[:7], exc_info=True)
            return None
        if not cache:
            return None
        try:
            stats = cache["metrics"]["time"]
            return RuntimeStatistics(**stats)
        except (KeyError, TypeError, ValueError):
            logger.debug(f"Failed to load runtime statistics for {job}", exc_info=True)
            return None


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
