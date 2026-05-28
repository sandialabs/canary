# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
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
    f = config.getoption("archive_name")
    if f is None:
        return
    dest = Path(f)
    mode: Literal["w:gz", "w"] = "w:gz" if str(dest).endswith((".tgz", ".tar.gz")) else "w"
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
                    relpath: Path
                    if path.is_relative_to(prefix):
                        relpath = path.relative_to(prefix)
                    else:
                        tmp = job.workspace.dir / path.relative_to(job.spec.file.parent)
                        relpath = tmp.relative_to(prefix)
                    tf.add(path, arcname=str(relpath), recursive=True)
