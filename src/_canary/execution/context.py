# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""What the executor and backends may touch while running a session."""

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Callable

if TYPE_CHECKING:
    from ..core.job import Job


@dataclasses.dataclass(frozen=True)
class ExecutionContext:
    """Paths and the result sink a backend needs to run one session.

    Backends receive it as ``runner.context`` and never see the workspace.  The
    session name is ``runner.session``.

    Attributes:
        root: Workspace root (the ``.canary`` directory).
        sessions_dir: Directory holding the session directories.
        cache_dir: Workspace cache directory.
        reports_dir: Directory reporters write into.
        record: Spool the job's current result to the database and sync the live
            view.  Safe to call more than once per job: an older result never
            replaces a newer one.
    """

    root: Path
    sessions_dir: Path
    cache_dir: Path
    reports_dir: Path
    record: Callable[["Job"], None]
