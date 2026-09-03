# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Results view management: per-session symlink/copy/hardlink trees of job output directories.

A *view* is a directory tree that presents the latest result for each job
in a human-navigable layout.  The root directory contains one entry per job,
named after the job's ``view_path`` (typically the test's relative path within
the workspace).

Three classes collaborate here:

* :class:`ViewSettings` — user-facing configuration (name, when, only, mode).
* :class:`ResultsView` — the view directory itself; knows how to create,
  update, and remove view entries.
* :class:`ViewManager` — orchestrates live updates during a session run,
  protected by a file lock for concurrent multi-process access.
"""

import dataclasses
import datetime
import fcntl
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Iterator
from typing import Literal
from typing import cast

from . import config
from .job import Job
from .util import logging
from .util.filesystem import force_remove

if TYPE_CHECKING:
    from .workspace import Session
    from .workspace import Workspace

ViewWhen = Literal["always", "never", "on_success", "on_failure"]
ViewOnly = Literal["all", "failed", "not_pass", "passed"]
ViewMode = Literal["symlink", "hardlink", "copy"]


logger = logging.get_logger(__name__)


@dataclasses.dataclass
class ViewSettings:
    """Configuration for a results view.

    Attributes:
        name: Directory name for the view, relative to the workspace parent.
            Must not contain a path separator.
        when: Condition under which the view is populated:
            ``'always'`` (default), ``'never'``, ``'on_success'``, or
            ``'on_failure'``.
        only: Which jobs to include: ``'all'``, ``'failed'``, ``'not_pass'``,
            or ``'passed'``.
        mode: How job output directories are linked into the view:
            ``'symlink'`` (default), ``'hardlink'``, or ``'copy'``.
    """

    name: str = "TestResults"
    when: ViewWhen = "always"
    only: ViewOnly = "all"
    mode: ViewMode = "symlink"

    @classmethod
    def default(cls) -> "ViewSettings":
        """Return a ``ViewSettings`` populated from the active canary configuration."""
        view_cfg = config.get("workspace:view") or {}
        name = str(view_cfg.get("name") or "TestResults")
        when = cast(ViewWhen, view_cfg.get("when") or "always")
        only = cast(ViewOnly, view_cfg.get("only") or "all")
        mode = cast(ViewMode, view_cfg.get("mode") or "symlink")
        return ViewSettings(name=name, when=when, only=only, mode=mode)

    def __serialize__(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "ViewSettings":
        return cls(**d)

    def __post_init__(self):
        """Validate field values against their allowed sets."""
        assert os.path.sep not in self.name
        assert self.when in {"always", "never", "on_success", "on_failure"}
        assert self.only in {"all", "failed", "not_pass", "passed"}
        assert self.mode in {"symlink", "hardlink", "copy"}

    def include_job(self, job: Job) -> bool:
        """Return ``True`` if *job* should be included in the view.

        Skipped jobs are always excluded.  Other jobs are filtered according to
        :attr:`only`.
        """
        if job.status.is_skipped():
            return False
        if self.only == "failed" and not job.status.is_failure():
            return False
        elif self.only == "passed" and not job.status.is_success():
            return False
        elif self.only == "not_pass" and job.status.is_success():
            return False
        return True

    def is_enabled(self, jobs: list[Job]) -> bool:
        """Return ``True`` if the view should be created/updated given *jobs*.

        Evaluates :attr:`when` against the aggregate job outcomes.
        """
        if self.when == "always":
            return True
        if self.when == "never":
            return False
        if self.when == "on_success":
            return all(job.status.is_success() or job.status.is_skipped() for job in jobs)
        if self.when == "on_failure":
            return any(job.status.is_failure() for job in jobs)
        return False

    def always_disabled(self) -> bool:
        """Return ``True`` if the view is unconditionally disabled (``when='never'``)."""
        return self.when == "never"

    def always_enabled(self) -> bool:
        """Return ``True`` if the view is unconditionally enabled (``when='always'``)."""
        return self.when == "always"

    def deferred_until_finish(self) -> bool:
        """Return ``True`` if the view update must wait until the session ends.

        This is the case when ``when`` is ``'on_success'`` or ``'on_failure'``
        because the decision cannot be made until all jobs have finished.
        """
        return self.when in {"on_success", "on_failure"}


@dataclasses.dataclass
class ViewManifestEntry:
    """Record of a single job's entry in the view manifest.

    Attributes:
        job_id: The spec ID of the job.
        view_path: Path of the entry relative to the view root directory.
        source: Absolute path to the job's workspace directory.
        session: Session ID string when this entry was last written.
        outcome: String name of the job's :class:`~_canary.status.Outcome`.
        updated: ISO 8601 UTC timestamp of when this entry was last updated.
    """

    job_id: str
    view_path: str
    source: str
    session: str
    outcome: str
    updated: str

    @classmethod
    def from_job(cls, job: Job) -> "ViewManifestEntry":
        assert job.workspace.session is not None
        return cls(
            job_id=job.id,
            view_path=str(job.view_path),
            source=str(job.workspace.dir),
            session=job.workspace.session,
            outcome=job.status.outcome.name,
            updated=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )


@dataclasses.dataclass
class ViewManifest:
    """JSON manifest that tracks which jobs are present in a view directory.

    Written to ``<view_dir>/.canary-view.json``.  Stores the current
    :class:`ViewSettings` alongside a mapping of job ID → :class:`ViewManifestEntry`
    so that stale entries can be removed when a job is re-run.

    Attributes:
        version: Manifest format version (currently ``1``).
        settings: Serialized :class:`ViewSettings` as a plain dict.
        entries: Mapping of job ID → entry record.
    """

    version: int = 1
    settings: dict[str, Any] = dataclasses.field(default_factory=dict)
    entries: dict[str, ViewManifestEntry] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ViewManifest":
        entries = {
            job_id: ViewManifestEntry(**entry) for job_id, entry in data.get("entries", {}).items()
        }
        return cls(
            version=data.get("version", 1), settings=data.get("settings", {}), entries=entries
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "settings": self.settings,
            "entries": {
                job_id: dataclasses.asdict(entry) for job_id, entry in self.entries.items()
            },
        }


@dataclasses.dataclass(frozen=True)
class ResultsView:
    """An on-disk results view rooted at a specific directory.

    Manages the lifecycle of a view directory: creation, per-job updates,
    manifest persistence, and removal.  The view directory is identified by a
    ``<root>/<settings.name>/`` path and is tagged with a
    ``.canary-view.json`` manifest file so canary can distinguish owning
    directories from user-created ones.

    Attributes:
        root: Parent directory; the view directory itself is ``root/settings.name``.
        settings: Configuration that controls which jobs are included and how
            they are linked.
    """

    root: Path
    settings: ViewSettings

    @staticmethod
    def exists_at(p: Path) -> bool:
        """Return ``True`` if *p* contains a ``.canary-view.json`` manifest."""
        return (p / ".canary-view.json").exists()

    def __serialize__(self) -> dict[str, Any]:
        # json_helper.Encoder will add ".type" automatically
        return {"root": self.root, "settings": self.settings}

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "ResultsView":
        return cls(root=Path(d["root"]), settings=d["settings"])

    @property
    def dir(self) -> Path:
        return (self.root / self.settings.name).resolve()

    def exists(self) -> bool:
        return self.dir.exists() and (self.dir / ".canary-view.json").exists()

    def make(self, exist_ok: bool = False) -> None:
        """Create the view directory, optionally tolerating an existing one.

        Args:
            exist_ok: If ``True``, do nothing when the view already exists.

        Raises:
            ValueError: If the directory exists but is not owned by this view,
                or if it already exists and ``exist_ok`` is ``False``.
        """
        tag = self.dir / ".canary-view.json"
        if self.dir.exists():
            if not tag.exists():
                raise ValueError("Cannot create view in non-owning directory")
            elif not exist_ok:
                raise ValueError(f"View already exists at {self.dir}")
            return
        self.dir.mkdir(parents=True, exist_ok=True)

    def unlink(self, missing_ok: bool = False) -> None:
        """Remove the view directory and all its contents.

        Args:
            missing_ok: If ``True``, do nothing when the view directory does
                not exist.

        Raises:
            ValueError: If the directory exists but is not owned by this view,
                or if it is missing and ``missing_ok`` is ``False``.
        """
        if not self.dir.exists():
            if not missing_ok:
                raise ValueError(f"View does not exist at {self.dir}")
            return
        tag = self.dir / ".canary-view.json"
        if self.dir.exists() and not tag.exists():
            raise ValueError("Cannot remove non-owning directory")
        force_remove(self.dir)

    def update(self, jobs: list[Job]) -> bool:
        """Synchronize all *jobs* into the view and save the manifest.

        Creates the view directory if it does not exist.  Jobs are filtered by
        :meth:`~ViewSettings.include_job` before being added.

        Args:
            jobs: All finished jobs to consider.

        Returns:
            ``True`` if any entry was added or removed, ``False`` if nothing
            changed (also ``False`` if the view is disabled for these jobs).
        """
        if not self.settings.is_enabled(jobs):
            return False

        if not self.exists():
            self.make(exist_ok=True)
            manifest = self.load_manifest()
            self.save_manifest(manifest)
        else:
            manifest = self.load_manifest()

        changed = False
        for job in jobs:
            if self.sync(job, manifest=manifest, save=False):
                changed = True
        if changed:
            self.save_manifest(manifest)
        return True

    def add(self, job: Job) -> None:
        """Add *job*'s output directory to the view using the configured mode.

        Creates parent directories as needed.  Any existing entry at the
        destination path is removed first.

        Args:
            job: The finished job whose workspace directory should be linked.
        """
        source = job.workspace.dir
        dest = self.dir / job.view_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.remove_path(dest)
        if self.settings.mode == "symlink":
            try:
                dest.symlink_to(source, target_is_directory=True)
            except FileExistsError:
                pass
        elif self.settings.mode == "hardlink":
            for src in source.rglob("*"):
                rel = src.relative_to(source)
                dst = dest / rel
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists() or dst.is_symlink():
                    dst.unlink()
                os.link(src, dst)
        elif self.settings.mode == "copy":
            shutil.copytree(source, dest, dirs_exist_ok=True, symlinks=False)

    @property
    def manifest_file(self) -> Path:
        return self.dir / ".canary-view.json"

    def load_manifest(self) -> ViewManifest:
        """Load and return the view manifest, or an empty one if it does not exist."""
        if not self.manifest_file.exists():
            return ViewManifest(settings=self.settings.__serialize__())
        with open(self.manifest_file) as fh:
            return ViewManifest.from_dict(json.load(fh))

    def save_manifest(self, manifest: ViewManifest) -> None:
        """Atomically write *manifest* to the ``.canary-view.json`` file.

        Uses a temp-file + ``os.replace`` pattern to avoid partial writes.
        Also performs a best-effort ``fsync`` on the directory fd for rename
        durability on network filesystems.
        """
        manifest.settings = self.settings.__serialize__()

        fd: int | None = None
        tmp_path: Path | None = None

        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{self.manifest_file.name}.", suffix=".tmp", dir=self.dir, text=True
            )
            tmp_path = Path(tmp_name)

            with os.fdopen(fd, "w") as fh:
                fd = None
                json.dump(manifest.to_dict(), fh, indent=2)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())

            os.replace(tmp_path, self.manifest_file)

            # Best-effort directory fsync for rename durability.
            try:
                dirfd = os.open(self.dir, os.O_DIRECTORY)
            except Exception as e:
                logger.debug(f"Failed to open {self.dir}", exc_info=e)
            else:
                try:
                    os.fsync(dirfd)
                finally:
                    os.close(dirfd)

        except Exception:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            raise

    def sync(self, job: Job, manifest: ViewManifest | None = None, *, save: bool = True) -> bool:
        """Synchronize this job's latest result into the view.

        This removes any previous entry for the job, then conditionally adds
        the current result depending on ViewSettings.include_job().
        """
        if not self.exists():
            self.make(exist_ok=True)
        manifest = manifest or self.load_manifest()
        changed = False
        if self.remove_entry(job.id, manifest):
            changed = True
        if self.settings.include_job(job):
            self.add(job)
            manifest.entries[job.id] = ViewManifestEntry.from_job(job)
            changed = True
        if save and changed:
            self.save_manifest(manifest)
        return changed

    def remove_entry(self, job_id: str, manifest: ViewManifest) -> bool:
        """Remove a job's entry from the view and from *manifest*.

        Args:
            job_id: The spec ID of the job to remove.
            manifest: The manifest to update in place.

        Returns:
            ``True`` if an entry was found and removed, ``False`` if the job
            was not in the manifest.
        """
        entry = manifest.entries.pop(job_id, None)
        if entry is None:
            return False

        dest = self._manifest_entry_path(entry)
        self.remove_path(dest)
        return True

    def _manifest_entry_path(self, entry: ViewManifestEntry) -> Path:
        rel = Path(entry.view_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"Invalid view manifest path: {entry.view_path!r}")
        return self.dir / rel

    def remove_path(self, path: Path) -> None:
        """Remove *path* from the view regardless of whether it is a file, symlink, or directory."""
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            force_remove(path)


@dataclasses.dataclass
class ViewManager:
    """Live manager for maintaining the session results view.

    The view is updated incrementally as jobs finish.  Updates are protected
    by a workspace-level file lock so multiple Canary processes can safely
    update the same view, e.g. re-entrant HPC batch runs.
    """

    workspace: "Workspace"
    settings: ViewSettings
    session: "Session | None" = None

    view: ResultsView | None = dataclasses.field(init=False, default=None)
    enabled: bool = dataclasses.field(init=False, default=False)
    started: bool = dataclasses.field(init=False, default=False)
    finished: bool = dataclasses.field(init=False, default=False)

    _finished_jobs: dict[str, Job] = dataclasses.field(init=False, default_factory=dict)

    @property
    def lock_file(self) -> Path:
        """Path to the exclusive advisory lock file used to serialise view updates."""
        return (self.workspace.cache_dir / "view.lock").resolve()

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Context manager that holds an exclusive ``flock`` on :attr:`lock_file`."""
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_file, "w") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def start(self) -> None:
        """Initialise the view manager at the start of a session.

        Creates the view directory (for ``always`` mode) or records that updates
        are deferred until session end.  Idempotent — safe to call multiple times.
        """
        if self.started:
            return
        self.started = True
        if self.settings.always_disabled():
            self.enabled = False
            return
        self.enabled = True
        self.view = ResultsView(root=self.workspace.root.parent, settings=self.settings)
        if self.settings.deferred_until_finish():
            logger.info(f"Deferring view update at {self.view.dir} until session finish")
            return
        with self.locked():
            logger.info(f"Updating live view at {self.view.dir}")
            self.view.make(exist_ok=True)
            manifest = self.view.load_manifest()
            self.view.save_manifest(manifest)
            # Preserve existing behavior: latest view settings are remembered.
            self.workspace.register_view(self.view)

    def finish(self) -> ResultsView | None:
        """Finalise the view at session end.

        For deferred views (``on_success`` / ``on_failure``) this is where the
        view is actually created.  For live views the manifest is flushed.
        Idempotent — safe to call multiple times; subsequent calls are no-ops.

        Returns:
            The :class:`ResultsView` that was written, or ``None`` if the view
            was disabled or the ``when`` condition was not met.
        """
        if self.finished:
            return self.view
        self.finished = True
        if not self.enabled or self.view is None:
            return None
        if self.settings.deferred_until_finish():
            jobs = list(self._finished_jobs.values())
            # Fallback for cases where sync callbacks did not populate _finished_jobs.
            if not jobs and self.session is not None:
                jobs = list(self.session.jobs)
            if not jobs:
                jobs = self.workspace.load_jobs()
            if not self.settings.is_enabled(jobs):
                logger.info(
                    f"View at {self.view.dir} not created because "
                    f"workspace result did not satisfy when={self.settings.when!r}"
                )
                return None
            with self.locked():
                try:
                    logger.info(f"Creating deferred view at {self.view.dir}")
                    self.view.update(jobs)
                    self.workspace.register_view(self.view)
                except json.JSONDecodeError:
                    logger.exception(
                        f"{self.view.manifest_file}: corrupt view manifest; "
                        "run `canary view rebuild` to repair the view"
                    )
            return self.view
        with self.locked():
            try:
                manifest = self.view.load_manifest()
            except json.JSONDecodeError:
                logger.exception(
                    f"{self.view.manifest_file}: corrupt view manifest; "
                    "run `canary view rebuild` to repair the view"
                )
                return self.view
            self.view.save_manifest(manifest)
        return self.view

    def sync(self, job: Job) -> None:
        """Record *job*'s result in the view immediately after it finishes.

        For deferred views (``on_success`` / ``on_failure``) the job is added
        to ``_finished_jobs`` for processing at :meth:`finish` time but no
        filesystem changes are made yet.  For live views the view entry is
        updated under the view lock.

        Args:
            job: The job that has just completed.
        """
        if not self.enabled:
            return
        self._finished_jobs[job.id] = job
        if self.view is None:
            raise RuntimeError("ViewManager is enabled but not initialized")
        if self.settings.deferred_until_finish():
            return
        with self.locked():
            manifest = self.view.load_manifest()
            changed = self.view.sync(job, manifest=manifest, save=False)
            if changed:
                self.view.save_manifest(manifest)

    def rebuild(self) -> ResultsView | None:
        """Rebuild the view from the latest results in the workspace.

        The entire rebuild is protected by the same view lock used for live
        updates, so live syncs cannot interleave with a rebuild.
        """
        jobs = self.workspace.load_jobs()
        with self.locked():
            old_view = self.workspace.latest_view()
            old_dir: Path | None = None
            bak_dir: Path | None = None
            if old_view is not None and old_view.exists():
                old_dir = old_view.dir
                bak_dir = old_dir.with_name(old_dir.name + ".tmp")
                if bak_dir.exists():
                    force_remove(bak_dir)
                os.rename(old_dir, bak_dir)
            made_new = False
            try:
                if self.settings.always_disabled():
                    made_new = False
                    return None
                view = ResultsView(root=self.workspace.root.parent, settings=self.settings)
                # There should not normally be an existing view at this path after
                # the backup rename. Keep this for robustness, e.g. changed view
                # name or stale partial directory.
                view.unlink(missing_ok=True)
                if view.update(jobs):
                    self.view = view
                    made_new = True
                    return view
                else:
                    view.unlink(missing_ok=True)
                    made_new = False
                    return None
            finally:
                if made_new:
                    if bak_dir is not None:
                        force_remove(bak_dir)
                else:
                    if bak_dir is not None and old_dir is not None:
                        if not old_dir.exists() and bak_dir.exists():
                            os.rename(bak_dir, old_dir)

    def __enter__(self) -> "ViewManager":
        """Start the view manager; calls :meth:`start`."""
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        """Finalise the view manager; calls :meth:`finish`."""
        self.finish()
