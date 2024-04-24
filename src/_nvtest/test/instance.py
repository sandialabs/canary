import dataclasses
import os
from types import SimpleNamespace
from typing import Any
from typing import Optional
from typing import Type
from typing import Union

from .case import TestCase
from .status import Status


class Parameters(SimpleNamespace):
    def __eq__(self, other: object) -> bool:
        if isinstance(other, (Parameters, SimpleNamespace)):
            return self == other
        assert isinstance(other, dict)
        if len(self.__dict__) != len(other):
            return False
        for key, value in other.items():
            if key not in self.__dict__:
                return False
            if self.__dict__[key] != value:
                return False
        return True


@dataclasses.dataclass(frozen=True)
class TestInstance:
    file_root: str
    file_path: str
    name: str
    file: str
    processors: int
    devices: int
    analyze: str
    family: str
    keywords: list[str]
    parameters: Parameters
    timeout: Union[None, float, int]
    runtime: Union[None, float, int]
    baseline: list[Union[str, tuple[str, str]]]
    sources: dict[str, list[tuple[str, str]]]
    exec_root: str
    exec_dir: str
    status: Status
    start: float
    finish: float
    id: str
    cmd_line: str
    returncode: int
    variables: dict[str, str]
    dependencies: list["TestInstance"]

    @classmethod
    def from_case(cls: Type["TestInstance"], case: TestCase) -> "TestInstance":
        dependencies: list[TestInstance] = []
        for dep in case.dependencies:
            dependencies.append(TestInstance.from_case(dep))
        self = cls(
            file_root=case.file_root,
            file_path=case.file_path,
            name=case.name,
            file=os.path.join(case.file_root, case.file_path),
            processors=case.processors,
            devices=case.devices,
            family=case.family,
            analyze=case.analyze or "",
            keywords=case.keywords(),
            parameters=Parameters(**case.parameters),
            timeout=case.timeout,
            runtime=case.runtime,
            baseline=case.baseline,
            sources=case.sources,
            exec_root=case.exec_root,  # type: ignore
            exec_dir=case.exec_dir,
            status=case.status,
            start=case.start,
            finish=case.finish,
            id=case.id,
            cmd_line=case.cmd_line,
            returncode=case.returncode,
            variables=case.variables,
            dependencies=dependencies,
        )
        return self

    @classmethod
    def load(cls: Type["TestInstance"], arg_path: Optional[str] = None) -> "TestInstance":
        if arg_path is None:
            arg_path = "./.nvtest/case.data.p"
        elif arg_path.endswith((".vvt", ".pyt")):
            arg_path = os.path.join(os.path.dirname(arg_path), ".nvtest/case.data.p")
        with open(arg_path, "rb") as fh:
            case = TestCase.load(fh)
        return TestInstance.from_case(case)

    def get_dependency(self, **params: Any) -> "Optional[TestInstance]":
        for dep in self.dependencies:
            if dep.parameters == params:
                return dep
        return None
