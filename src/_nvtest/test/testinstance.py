import dataclasses
import os
from typing import Optional
from typing import Type
from typing import Union

from .enums import Result
from .enums import Skip
from .testcase import TestCase


@dataclasses.dataclass(frozen=True)
class TestInstance:
    file_root: str
    file_path: str
    name: str
    file: str
    size: int
    analyze: str
    family: str
    keywords: list[str]
    parameters: dict[str, object]
    timeout: Union[None, int]
    runtime: Union[None, float, int]
    skip: Skip
    baseline: list[tuple[str, str]]
    sources: dict[str, list[tuple[str, str]]]
    exec_root: str
    exec_dir: str
    result: Result
    start: float
    finish: float
    id: str
    cmd_line: str
    returncode: int
    variables: dict[str, str]
    dependencies: list["TestCase"]

    @classmethod
    def load(
        cls: Type["TestInstance"], arg_path: Optional[str] = None
    ) -> "TestInstance":
        case = TestCase.load(arg_path)
        self = cls(
            root=case.file_root,
            path=case.file_path,
            name=case.name,
            file=os.path.join(case.file_root, case.file_path),
            size=case.size,
            family=case.family,
            analyze=case.analyze or "",
            keywords=case.keywords,
            parameters=case.parameters,
            timeout=case.timeout,
            runtime=case.runtime,
            skip=case.skip,
            baseline=case.baseline,
            sources=case.sources,
            exec_root=case.exec_root,  # type: ignore
            exec_dir=case.exec_dir,
            result=case.result,
            start=case.start,
            finish=case.finish,
            id=case.id,
            cmd_line=case.cmd_line,
            returncode=case.returncode,
            variables=case.variables,
            dependencies=case.dependencies,
        )
        return self
