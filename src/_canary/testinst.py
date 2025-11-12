# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import io
import os
from typing import TYPE_CHECKING
from typing import Any
from typing import Type

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
    baseline: list[dict]
    sources: dict[str, list[tuple[str, str | None]]]
    work_tree: str
    working_directory: str
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
        with open(self.lockfile) as fh:
            state = json.load(fh)
        self.attributes.update(kwargs)
        state["spec"].setdefault("attributes").update(self.attributes)
        with open(self.lockfile, "w") as fh:
            json.dump(state, fh, indent=2)

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


def factory(case: "TestCase") -> TestInstance:
    dependencies: list[TestInstance] = []
    for dep in case.dependencies:
        dependencies.append(factory(dep))

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
        sources.setdefault(asset.action, []).append((asset.src, asset.dst))
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
        status=case.status,
        start=case.timekeeper.started_on,
        stop=case.timekeeper.finished_on,
        id=case.spec.id,
        returncode=case.status.code,
        variables=case.spec.environment,
        dependencies=dependencies,
        ofile=case.workspace.stdout,
        efile=case.workspace.stderr,
        lockfile=str(case.workspace.dir / "testcase.lock"),
    )
    return instance
