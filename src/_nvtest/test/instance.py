import dataclasses
import os
from typing import Any
from typing import Generator
from typing import Optional
from typing import Type
from typing import Union

from .case import AnalyzeTestCase
from .case import TestCase
from .case import load as load_testcase
from .status import Status


class Parameters:
    def __init__(self, **kwargs: Any) -> None:
        self._keys: list[Union[tuple[str, ...], str]] = list(kwargs.keys())
        self._values: list[Any] = list(kwargs.values())

    def __str__(self) -> str:
        s = ", ".join(f"{k}={v}" for k, v in self.items())
        return f"Parameters({s})"

    def __contains__(self, key: Union[tuple[str, ...], str]) -> bool:
        return key in self._keys

    def __getitem__(self, key: Union[tuple[str, ...], str]) -> Any:
        if key not in self._keys:
            raise KeyError(key)
        i = self._keys.index(key)
        return self._values[i]

    def __setitem__(self, key: Union[tuple[str, ...], str], value: Any) -> None:
        self._keys.append(key)
        self._values.append(value)

    def __getattr__(self, key: str) -> Any:
        if key not in self._keys:
            raise AttributeError(f"Parameters object has no attribute {key!r}")
        index = self._keys.index(key)
        return self._values[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Parameters):
            return self._keys == other._keys and self._values == other._values
        assert isinstance(other, dict)
        if len(self._keys) != len(other):
            return False
        for key, value in other.items():
            if key not in self._keys:
                return False
            if self._keys[key] != value:
                return False
        return True

    def items(self) -> Generator[Any, None, None]:
        for i, key in enumerate(self._keys):
            yield key, self._values[i]

    def keys(self) -> list:
        return list(self._keys)

    def values(self) -> list:
        return list(self._values)

    def get(
        self, key: Union[tuple[str, ...], str], default: Optional[Any] = None
    ) -> Optional[Any]:
        if key in self._keys:
            index = self._keys.index(key)
            return self._values[index]
        return default

    def asdict(self) -> dict[Union[tuple[str, ...], str], Any]:
        d: dict[Union[tuple[str, ...], str], Any] = {}
        for i, key in enumerate(self._keys):
            d[key] = self._values[i]
        return d


@dataclasses.dataclass(frozen=True)
class TestInstance:
    file_root: str
    file_path: str
    name: str
    file: str
    cpu_ids: list[int]
    gpu_ids: list[int]
    analyze: bool
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
    cmd_line: Optional[str]
    returncode: int
    variables: dict[str, str]
    dependencies: list["TestInstance"]

    @classmethod
    def from_case(cls: Type["TestInstance"], case: TestCase) -> "TestInstance":
        dependencies: list[TestInstance] = []
        for dep in case.dependencies:
            dependencies.append(TestInstance.from_case(dep))
        parameters: Parameters
        if not isinstance(case, AnalyzeTestCase):
            parameters = Parameters(**case.parameters)
        else:
            parameters = Parameters()
            keys = tuple(case.dependencies[0].parameters.keys())
            if len(keys) == 1:
                parameters[keys[0]] = tuple([dep.parameters[keys[0]] for dep in case.dependencies])
            else:
                table = []
                for dep in case.dependencies:
                    row = []
                    for key in keys:
                        row.append(dep.parameters[key])
                    table.append(tuple(row))
                parameters[keys] = tuple(table)
                for i, key in enumerate(keys):
                    parameters[key] = tuple([row[i] for row in table])

        self = cls(
            file_root=case.file_root,
            file_path=case.file_path,
            name=case.name,
            file=os.path.join(case.file_root, case.file_path),
            cpu_ids=case.cpu_ids,
            gpu_ids=case.gpu_ids,
            family=case.family,
            analyze=isinstance(case, AnalyzeTestCase),
            keywords=case.keywords,
            parameters=parameters,
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

    @property
    def processors(self) -> int:
        return self.cpus

    @property
    def cpus(self) -> int:
        return len(self.cpu_ids)

    @property
    def gpus(self) -> int:
        return len(self.gpu_ids)

    @classmethod
    def load(cls: Type["TestInstance"], arg_path: Optional[str] = None) -> "TestInstance":
        dbf = TestCase._dbfile
        if arg_path is None:
            arg_path = dbf
        elif arg_path.endswith((".vvt", ".pyt")):
            arg_path = os.path.join(os.path.dirname(arg_path), dbf)
        with open(arg_path, "r") as fh:
            case = load_testcase(fh)
        return TestInstance.from_case(case)

    def get_dependency(self, **params: Any) -> "Optional[TestInstance]":
        for dep in self.dependencies:
            if dep.parameters == params:
                return dep
        return None
