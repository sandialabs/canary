# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import datetime
import dataclasses
import io
import os
from pathlib import Path
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
        start=datetime.datetime.fromisoformat(case.timekeeper.started_on).timestamp(),
        stop=datetime.datetime.fromisoformat(case.timekeeper.finished_on).timestamp(),
        id=case.spec.id,
        returncode=case.status.code,
        variables=case.spec.environment,
        dependencies=dependencies,
        ofile=case.stdout,
        efile=case.stderr,
        lockfile=str(case.workspace.dir / "testcase.lock"),
    )
    return instance


def from_lock(lock: dict[str, Any], lookup: dict[str, TestInstance]) -> TestInstance:
    spec = lock["spec"]
    dependencies: list[TestInstance] = []
    for dep in spec["dependencies"]:
        dependencies.append(lookup[dep["id"]])
    parameters: Parameters
    cls: Type[TestInstance]
    if lock["spec"]["attributes"].get("multicase"):
        cls = TestMultiInstance
        columns: dict[str, list[Any]] = {}
        for key in spec["dependencies"][0]["parameters"].keys():
            col = columns.setdefault(key, [])
            for dep in spec["dependencies"]:
                col.append(dep["parameters"][key])
        parameters = MultiParameters(**columns)
    else:
        cls = TestInstance
        parameters = Parameters(**spec["parameters"])
    sources: dict[str, list[tuple[str, str | None]]] = {}
    for asset in spec["assets"]:
        sources.setdefault(asset["action"], []).append((asset["src"], asset["dst"]))

    workspace = lock["workspace"]
    status = lock["status"]
    resources = lock["resources"]
    timekeeper = lock["timekeeper"]

    instance = cls(
        file_root=spec["file_root"],
        file_path=spec["file_path"],
        name=spec["name"],
        file=os.path.join(spec["file_root"], spec["file_path"]),
        cpu_ids=[str(_["id"]) for _ in resources.get("cpus", [])],
        gpu_ids=[str(_["id"]) for _ in resources.get("gpus", [])],
        family=spec["family"],
        keywords=spec["keywords"],
        parameters=parameters,
        timeout=spec["timeout"],
        runtime=lock["runtime"],
        baseline=spec["baseline"],
        sources=sources,
        work_tree=str(workspace["dir"]),
        working_directory=str(workspace["dir"]),
        status=Status(status["name"], status["message"], status["code"]),
        start=timekeeper["started_on"],
        stop=timekeeper["finished_on"],
        id=spec["id"],
        returncode=status["code"],
        variables=spec["environment"],
        dependencies=dependencies,
        ofile=lock["stdout"],
        efile=lock["stderr"],
        lockfile=os.path.join(lock["workspace"]["dir"], "testcase.lock"),
    )
    return instance


def load_instance(
    arg: Path | str | None, lookup: dict[str, TestInstance] | None = None
) -> TestInstance:
    lookup = lookup or {}
    path = Path(arg or ".").absolute()
    file = path / "testcase.lock" if path.is_dir() else path
    lock_data = json.loads(file.read_text())
    for f in lock_data["dependencies"]:
        inst = load_instance(f, lookup)
        lookup[inst.id] = inst
    return from_lock(lock_data, lookup)
