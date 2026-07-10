# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

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

from . import config
from .job import Job
from .util import logging
from .util.filesystem import force_remove
from .util.filesystem import write_directory_tag

if TYPE_CHECKING:
    from .workspace import Session
    from .workspace import Workspace

logger = logging.get_logger(__name__)

view_tag = "VIEW.TAG"


@dataclasses.dataclass
class ViewSettings:
    name: str = "TestResults"
    when: Literal["always", "never"] = "always"
    only: Literal["all", "failed", "not_pass", "passed"] = "all"
    mode: Literal["symlink", "hardlink", "copy"] = "symlink"
    reports: list[str] = dataclasses.field(default_factory=lambda: ["html"])

    @classmethod
    def default(cls) -> "ViewSettings":
        view_cfg = config.get("workspace:view") or {}
        name = view_cfg.get("name") or "TestResults"
        when = view_cfg.get("when") or "always"
        only = view_cfg.get("only") or "all"
        mode = view_cfg.get("mode") or "symlink"
        reports = view_cfg.get("reports") or ["html"]
        return ViewSettings(name=name, when=when, only=only, mode=mode, reports=reports)

    def __serialize__(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def __deserialize__(cls, d: dict[str, Any]) -> "ViewSettings":
        return cls(**d)

    def __post_init__(self):
        assert os.path.sep not in self.name
        assert self.when in {"always", "never"}
        assert self.only in {"all", "failed", "not_pass", "passed"}
        assert self.mode in {"symlink", "hardlink", "copy"}
        assert all([x in {"html", "markdown", "none"} for x in self.reports])

    def include_job(self, job: Job) -> bool:
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
        return self.when == "always"

    def always_disabled(self) -> bool:
        return self.when == "never"

    def always_enabled(self) -> bool:
        return self.when == "always"


@dataclasses.dataclass
class ViewManifestEntry:
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
    root: Path
    settings: ViewSettings

    @staticmethod
    def exists_at(p: Path) -> bool:
        return (p / view_tag).exists()

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
        return self.dir.exists() and (self.dir / view_tag).exists()

    def make(self, exist_ok: bool = False) -> None:
        tag = self.dir / view_tag
        if self.dir.exists():
            if not tag.exists():
                raise ValueError("Cannot create view in non-owning directory")
            elif not exist_ok:
                raise ValueError(f"View already exists at {self.dir}")
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        write_directory_tag(tag)

    def unlink(self, missing_ok: bool = False) -> None:
        if not self.dir.exists():
            if not missing_ok:
                raise ValueError(f"View does not exist at {self.dir}")
            return
        tag = self.dir / view_tag
        if self.dir.exists() and not tag.exists():
            raise ValueError("Cannot remove non-owning directory")
        force_remove(self.dir)

    def update(self, jobs: list[Job]) -> bool:
        if not self.settings.is_enabled(jobs):
            return False
        if not self.exists():
            self.make(exist_ok=True)
        manifest = self.load_manifest()
        changed = False
        for job in jobs:
            if self.sync(job, manifest=manifest, save=False):
                changed = True
        if changed:
            self.save_manifest(manifest)
        return True

    def add(self, job: Job) -> None:
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
    def metadata_dir(self) -> Path:
        return self.dir / "_canary"

    @property
    def manifest_file(self) -> Path:
        return self.metadata_dir / "view.json"

    def load_manifest(self) -> ViewManifest:
        if not self.manifest_file.exists():
            return ViewManifest(settings=self.settings.__serialize__())
        with open(self.manifest_file) as fh:
            return ViewManifest.from_dict(json.load(fh))

    def save_manifest(self, manifest: ViewManifest) -> None:
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        manifest.settings = self.settings.__serialize__()

        fd: int | None = None
        tmp_path: Path | None = None

        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{self.manifest_file.name}.",
                suffix=".tmp",
                dir=self.metadata_dir,
                text=True,
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
                dirfd = os.open(self.metadata_dir, os.O_DIRECTORY)
            except Exception:  # nosec B110
                pass
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
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            force_remove(path)


@dataclasses.dataclass
class ViewReportRequest:
    workspace: "Workspace"
    view: ResultsView
    formats: tuple[str, ...]
    reason: Literal["finish", "rebuild", "command"] = "finish"
    output_dir: Path | None = None


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

    @property
    def lock_file(self) -> Path:
        return (self.workspace.cache_dir / "view.lock").resolve()

    @contextmanager
    def locked(self) -> Iterator[None]:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_file, "w") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def start(self) -> None:
        if self.started:
            return
        self.started = True

        if self.settings.always_disabled():
            self.enabled = False
            return

        self.enabled = True
        self.view = ResultsView(root=self.workspace.root.parent, settings=self.settings)

        with self.locked():
            logger.info(f"Updating live view at {self.view.dir}")
            self.view.make(exist_ok=True)

            manifest = self.view.load_manifest()
            self.view.save_manifest(manifest)

            # Preserve existing behavior: latest view settings are remembered.
            self.workspace.register_view(self.view)

    def finish(self) -> ResultsView | None:
        if self.finished:
            return self.view
        self.finished = True

        if not self.enabled or self.view is None:
            return None

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

            # report hook, if present, would go here

        return self.view

    def sync(self, job: Job) -> None:
        if not self.enabled:
            return
        if self.view is None:
            raise RuntimeError("ViewManager is enabled but not initialized")
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
                    return
                view = ResultsView(root=self.workspace.root.parent, settings=self.settings)
                # There should not normally be an existing view at this path after
                # the backup rename. Keep this for robustness, e.g. changed view
                # name or stale partial directory.
                view.unlink(missing_ok=True)
                view.make()
                if view.update(jobs):
                    self.view = view
                    made_new = True
                    if self.workspace.canary_level == 0:
                        self.report(reason="rebuild")
                    return view
                else:
                    view.unlink(missing_ok=True)
                    made_new = False
            finally:
                if made_new:
                    if bak_dir is not None:
                        force_remove(bak_dir)
                else:
                    if bak_dir is not None and old_dir is not None:
                        if not old_dir.exists() and bak_dir.exists():
                            os.rename(bak_dir, old_dir)

    def report(self, *, reason: Literal["finish", "rebuild", "command"]) -> None:
        if self.view is None:
            return
        formats = tuple(self.settings.reports)
        if not formats or "none" in formats:
            return
        request = ViewReportRequest(
            workspace=self.workspace,
            view=self.view,
            formats=formats,
            reason=reason,
            output_dir=self.view.metadata_dir / "reports",
        )
        config.pluginmanager.hook.canary_view_report(request=request)

    def __enter__(self) -> "ViewManager":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.finish()
