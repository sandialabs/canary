# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from ..workspace.workspace import Workspace
from .failure_analysis import list_existing_logs

if TYPE_CHECKING:
    from ..core.job import Job
    from ..core.jobspec import JobSpec


def remap_path(path: str | Path, *, root_at_creation: str | None, current_root: str | Path) -> str:
    text = str(path)
    if not root_at_creation:
        return text
    current = str(Path(current_root))
    if text.startswith(root_at_creation):
        return current + text[len(root_at_creation) :]
    return text


def locate(
    testspecs: list[str],
    *,
    show_input: bool = False,
    show_source_dir: bool = False,
    show_log: bool = False,
) -> list[dict[str, str]]:
    """Return ``{"id", "path"}`` for each of *testspecs* in the current workspace.

    The path is the job's view entry if it exists, else its session directory;
    with *show_log* its first log file; with *show_input* / *show_source_dir* the
    spec's input file or its directory.  Paths recorded under the workspace root
    at session creation are remapped to the current root (the workspace may have
    moved).
    """
    workspace = Workspace.load()
    root_at_creation = None
    latest = workspace.refs_dir / "latest"
    if latest.exists():
        lock = workspace.sessions_dir / latest.read_text().strip() / "session.lock"
        if lock.exists():
            root_at_creation = json.loads(lock.read_text()).get("root_at_creation")
    items = []
    for testspec in testspecs:
        f: Path | str
        if show_input or show_source_dir:
            spec: JobSpec = workspace.find(spec=testspec)
            f = spec.file if show_input else spec.file.parent
            items.append(
                {
                    "id": spec.id,
                    "path": remap_path(
                        f, root_at_creation=root_at_creation, current_root=workspace.root.parent
                    ),
                }
            )
        else:
            job: Job = workspace.find(job=testspec)
            if show_log:
                logs = list_existing_logs(job)
                f = Path(logs[0]["path"]) if logs else job.workspace.joinpath(job.stdout)
            else:
                if (view := workspace.latest_view()) and (view.dir / job.view_path).exists():
                    f = view.dir / job.view_path
                else:
                    f = job.workspace.dir
            items.append(
                {
                    "id": job.id,
                    "path": remap_path(
                        f, root_at_creation=root_at_creation, current_root=workspace.root.parent
                    ),
                }
            )
    return items
