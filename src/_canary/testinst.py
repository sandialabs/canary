# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import io
import os
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Type

from .job import JobState
from .jobspec import BaselineAction
from .status import Status
from .util import json_helper as json
from .util.paramview import MultiParameters
from .util.paramview import Parameters

if TYPE_CHECKING:
    from .job import Job


@dataclasses.dataclass(frozen=True)
class TestInstance:
    file_root: str
    file_path: str
    name: str
    file: str
    cpu_ids: list[str]
    gpu_ids: list[str]
    family: str
    keywords: list[str]
    parameters: Parameters
    timeout: float | int | None
    runtime: float | int | None
    baseline: list[BaselineAction]
    sources: dict[str, list[tuple[str, str | None]]]
    work_tree: str
    working_directory: str
    state: JobState
    status: Status
    start: float
    stop: float
    id: str
    returncode: int
    variables: dict[str, str]
    dependencies: list["TestInstance"]
    ofile: str
    efile: str | None
    lockfile: str
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def analyze(self) -> bool:
        # compatibility with vvtest
        return False

    @property
    def multicase(self) -> bool:
        # compatibility with vvtest
        return False

    def logfile(self, stage: str = "run") -> str:
        return os.path.join(self.working_directory, self.ofile)

    def output(self) -> str:
        fo = io.StringIO()
        if self.ofile and os.path.exists(os.path.join(self.working_directory, self.ofile)):
            fo.write("Captured stdout:\n")
            with open(os.path.join(self.working_directory, self.ofile)) as fh:
                fo.write(fh.read())
        if self.efile and os.path.exists(os.path.join(self.working_directory, self.efile)):
            fo.write("\nCaptured stderr:\n")
            with open(os.path.join(self.working_directory, self.efile)) as fh:
                fo.write(fh.read())
        return fo.getvalue()

    @property
    def processors(self) -> int:
        return self.cpus

    @property
    def cpus(self) -> int:
        return len(self.cpu_ids)

    @property
    def gpus(self) -> int:
        return len(self.gpu_ids)

    def set_attribute(self, **kwargs: Any) -> None:
        job: Job
        with open(self.lockfile) as fh:
            job = json.load(fh)
        self.attributes.update(kwargs)
        job.spec.attributes.update(self.attributes)
        with open(self.lockfile, "w") as fh:
            json.dump(job, fh, indent=2)

    def get_dependency(self, **params: Any) -> "TestInstance | None":
        for dep in self.dependencies:
            if dep.parameters == params:
                return dep
        return None


class TestMultiInstance(TestInstance):
    @property
    def analyze(self) -> bool:
        # compatibility with vvtest
        return True

    @property
    def multicase(self) -> bool:
        # compatibility with vvtest
        return True


def from_job(job: "Job") -> TestInstance:
    dependencies: list[TestInstance] = []
    for dep in job.dependencies:
        dependencies.append(from_job(dep))

    parameters: Parameters
    cls: Type[TestInstance]
    if job.spec.attributes.get("multicase"):
        cls = TestMultiInstance
        columns: dict[str, list[Any]] = {}
        for key in job.dependencies[0].spec.parameters.keys():
            col = columns.setdefault(key, [])
            for dep in job.dependencies:
                col.append(dep.spec.parameters[key])
        parameters = MultiParameters(**columns)
    else:
        cls = TestInstance
        parameters = Parameters(**job.spec.parameters)

    sources: dict[str, list[tuple[str, str | None]]] = {}
    for asset in job.spec.assets:
        sources.setdefault(asset.action, []).append((str(asset.src), asset.dst))
    start = job.timekeeper.started
    stop = job.timekeeper.finished
    instance = cls(
        file_root=str(job.spec.file_root),
        file_path=str(job.spec.file_path),
        name=job.spec.name,
        file=os.path.join(str(job.spec.file_root), str(job.spec.file_path)),
        cpu_ids=job.cpu_ids,
        gpu_ids=job.gpu_ids,
        family=job.spec.family,
        keywords=job.spec.keywords,
        parameters=parameters,
        timeout=job.spec.timeout,
        runtime=job.runtime,
        baseline=job.spec.baseline,
        sources=sources,
        work_tree=str(job.workspace.dir),  # type: ignore
        working_directory=str(job.workspace.dir),
        state=job.state,
        status=job.status,
        start=start,
        stop=stop,
        id=job.spec.id,
        returncode=job.status.code,
        variables={key: var for key, var in job.variables.items() if var is not None},
        dependencies=dependencies,
        ofile=job.stdout,
        efile=job.stderr,
        lockfile=str(job.workspace.dir / "testcase.lock"),
    )
    return instance


def load_instance(
    arg: Path | str | None, lookup: dict[str, TestInstance] | None = None
) -> TestInstance:
    lookup = lookup or {}
    path = Path(arg or ".").absolute()
    file = path / "testcase.lock" if path.is_dir() else path
    job = json.loads(file.read_text())
    return from_job(job)
