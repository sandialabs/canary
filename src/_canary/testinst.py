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
    from .testcase import TestCase


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
        job: TestCase
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


def from_testcase(case: "TestCase") -> TestInstance:
    dependencies: list[TestInstance] = []
    for dep in case.dependencies:
        dependencies.append(from_testcase(dep))

    parameters: Parameters
    cls: Type[TestInstance]
    if case.spec.attributes.get("multicase"):
        cls = TestMultiInstance
        columns: dict[str, list[Any]] = {}
        for key in case.dependencies[0].spec.parameters.keys():
            col = columns.setdefault(key, [])
            for dep in case.dependencies:
                col.append(dep.spec.parameters[key])
        parameters = MultiParameters(**columns)
    else:
        cls = TestInstance
        parameters = Parameters(**case.spec.parameters)

    sources: dict[str, list[tuple[str, str | None]]] = {}
    for asset in case.spec.assets:
        sources.setdefault(asset.action, []).append((str(asset.src), asset.dst))
    start = case.timekeeper.started
    stop = case.timekeeper.finished
    instance = cls(
        file_root=str(case.spec.file_root),
        file_path=str(case.spec.file_path),
        name=case.spec.name,
        file=os.path.join(str(case.spec.file_root), str(case.spec.file_path)),
        cpu_ids=case.cpu_ids,
        gpu_ids=case.gpu_ids,
        family=case.spec.family,
        keywords=case.spec.keywords,
        parameters=parameters,
        timeout=case.spec.timeout,
        runtime=case.runtime,
        baseline=case.spec.baseline,
        sources=sources,
        work_tree=str(case.workspace.dir),  # type: ignore
        working_directory=str(case.workspace.dir),
        state=case.state,
        status=case.status,
        start=start,
        stop=stop,
        id=case.spec.id,
        returncode=case.status.code,
        variables={key: var for key, var in case.variables.items() if var is not None},
        dependencies=dependencies,
        ofile=case.stdout,
        efile=case.stderr,
        lockfile=str(case.workspace.dir / "testcase.lock"),
    )
    return instance


def load_instance(
    arg: Path | str | None, lookup: dict[str, TestInstance] | None = None
) -> TestInstance:
    lookup = lookup or {}
    path = Path(arg or ".").absolute()
    file = path / "testcase.lock" if path.is_dir() else path
    case = json.loads(file.read_text())
    return from_testcase(case)
