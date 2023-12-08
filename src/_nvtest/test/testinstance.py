import dataclasses
import json
import os
from types import SimpleNamespace
from typing import Optional
from typing import Type
from typing import Union

from .status import Status
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
    parameters: SimpleNamespace
    timeout: Union[None, int]
    runtime: Union[None, float, int]
    baseline: list[tuple[str, str]]
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
    dependencies: list["TestCase"]

    @classmethod
    def load(
        cls: Type["TestInstance"], arg_path: Optional[str] = None
    ) -> "TestInstance":
        if arg_path is None:
            arg_path = "./.nvtest/case.json"
        elif arg_path.endswith((".vvt", ".pyt")):
            arg_path = os.path.join(os.path.dirname(arg_path), ".nvtest/case.json")
        with open(arg_path) as fh:
            kwds = json.load(fh)
        case = TestCase.from_dict(kwds)
        self = cls(
            file_root=case.file_root,
            file_path=case.file_path,
            name=case.name,
            file=os.path.join(case.file_root, case.file_path),
            size=case.size,
            family=case.family,
            analyze=case.analyze or "",
            keywords=case.keywords(),
            parameters=SimpleNamespace(**case.parameters),
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
            dependencies=case.dependencies,
        )
        return self
