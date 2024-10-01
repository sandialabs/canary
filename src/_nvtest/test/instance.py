import dataclasses
import os
from typing import Any
from typing import Generator
from typing import Optional
from typing import Type
from typing import Union

from .case import TestCase
from .case import TestMultiCase
from .case import load as load_testcase
from .status import Status

key_type = Union[tuple[str, ...], str]
index_type = Union[tuple[int, ...], int]


class Parameters:
    """Store parameters for a single test instance (case)

    Examples:

      >>> p = Parameters(a=1, b=2, c=3)
      >>> p['a']
      1
      >>> assert p.a == p['a']
      >>> p[('a', 'b')]
      (1, 2)
      >>> assert p['a,b'] == p[('a', 'b')]
      >>> p[('b', 'c', 'a')]
      (2, 3, 1)

    """

    def __init__(self, **kwargs: Any) -> None:
        self._keys: list[str] = list(kwargs.keys())
        self._values: list[Any] = list(kwargs.values())

    def __str__(self) -> str:
        name = self.__class__.__name__
        s = ", ".join(f"{k}={v}" for k, v in self.items())
        return f"{name}({s})"

    def __contains__(self, arg: key_type) -> bool:
        return self.multi_index(arg) is not None

    def __getitem__(self, arg: key_type) -> Any:
        ix = self.multi_index(arg)
        if ix is None:
            raise KeyError(arg)
        elif isinstance(ix, int):
            return self._values[ix]
        return tuple([self._values[i] for i in ix])

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

    def multi_index(self, arg: key_type) -> Optional[index_type]:
        keys: tuple[str, ...]
        if isinstance(arg, str):
            if arg in self._keys:
                value = self._keys.index(arg)
                if isinstance(value, list):
                    return tuple(value)
                return value
            elif "," in arg:
                keys = tuple(arg.split(","))
            else:
                return None
        else:
            keys = tuple(arg)
        return tuple([self._keys.index(key) for key in keys])

    def items(self) -> Generator[Any, None, None]:
        for i, key in enumerate(self._keys):
            yield key, self._values[i]

    def keys(self) -> list[str]:
        return list(self._keys)

    def values(self) -> list[Any]:
        return list(self._values)

    def get(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        try:
            return self[key]
        except KeyError:
            return default

    def asdict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for i, key in enumerate(self._keys):
            d[key] = self._values[i]
        return d


class MultiParameters(Parameters):
    """Store parameters for a single test instance (case)

    Examples:

      >>> p = Parameters(a=[1, 2, 3], b=[4, 5, 6], c=[7, 8, 9])
      >>> a = p['a']
      >>> a
      (1, 2, 3)
      >>> b = p['b']
      >>> b
      (4, 5, 6)
      >>> for i, values in enumerate(p[('a', 'b')]):
      ...     assert values == (a[i], b[i])
      ...     print(values)
      (1, 4)
      (2, 5)

      As a consequence of the above, note the following:

      >>> x = p[('a',)]
      >>> x
      ((1,), (2,), (3,))

      etc.

    """

    def __init__(self, **kwargs: Any) -> None:
        self._keys: list[str] = list(kwargs.keys())
        it = iter(kwargs.values())
        p_len = len(next(it))
        if not all(len(p) == p_len for p in it):
            raise ValueError(f"{self.__class__.__name__}: all arguments must be the same length")
        self._values: list[Any] = [tuple(_) for _ in kwargs.values()]

    def __getitem__(self, arg: key_type) -> Any:
        ix = self.multi_index(arg)
        if ix is None:
            raise KeyError(arg)
        elif isinstance(ix, int):
            return self._values[ix]
        rows = [self._values[i] for i in ix]
        # return colum data, now row data
        columns = tuple(zip(*rows))
        return columns


@dataclasses.dataclass(frozen=True)
class TestInstance:
    file_root: str
    file_path: str
    name: str
    file: str
    cpu_ids: list[int]
    gpu_ids: list[int]
    multicase: bool
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

    @property
    def analyze(self) -> bool:
        # compatibility with nvtest
        return self.multicase

    @classmethod
    def from_case(cls: Type["TestInstance"], case: TestCase) -> "TestInstance":
        dependencies: list[TestInstance] = []
        for dep in case.dependencies:
            dependencies.append(TestInstance.from_case(dep))
        parameters: Parameters
        if not isinstance(case, TestMultiCase):
            parameters = Parameters(**case.parameters)
        else:
            columns: dict[str, list[Any]] = {}
            for key in case.dependencies[0].parameters.keys():
                col = columns.setdefault(key, [])
                for dep in case.dependencies:
                    col.append(dep.parameters[key])
            parameters = MultiParameters(**columns)

        self = cls(
            file_root=case.file_root,
            file_path=case.file_path,
            name=case.name,
            file=os.path.join(case.file_root, case.file_path),
            cpu_ids=case.cpu_ids,
            gpu_ids=case.gpu_ids,
            family=case.family,
            multicase=isinstance(case, TestMultiCase),
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
