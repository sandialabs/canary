# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
import tarfile
from pathlib import Path
from typing import Literal

from ... import config
from ...config.argparsing import Parser
from ...hookspec import hookimpl
from ...workspace import Session


@hookimpl
def canary_addoption(parser: Parser) -> None:
    parser.add_argument(
        "--archive",
        metavar="NAME",
        dest="archive_name",
        command="run",
        help="Archive job artifacts to a tgz archive by this name",
    )


@hookimpl
def canary_sessionfinish(session: Session) -> None:
    if (var := os.getenv("CANARY_LEVEL")) and int(var) > 0:
        return
    if f := config.getoption("archive_name"):
        dest = Path(f)
    else:
        return
    mode: Literal["w:gz", "w"] = "w:gz" if str(dest).endswith((".tgz", ".gz")) else "w"
    prefix = Path(session.prefix)
    dest.parent.mkdir(exist_ok=True, parents=True)
    seen: set[Path] = set()
    with tarfile.open(dest, mode, dereference=True) as tf:
        for job in session.jobs:
            if not job.workspace.dir.exists():
                continue
            for artifact in job.spec.artifacts:
                if not artifact.active(job.status):
                    continue
                for path in job.workspace.dir.glob(artifact.pattern):
                    rp = path.resolve()
                    if rp in seen:
                        continue
                    seen.add(rp)
                    relpath = path.relative_to(prefix)
                    tf.add(path, arcname=str(relpath), recursive=True)
