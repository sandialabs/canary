import errno
import itertools
import json
import os
import sys
import time
from copy import deepcopy
from string import Template
from typing import Any
from typing import Optional
from typing import Union

from ..compat.vvtest import write_vvtest_util
from ..util import filesystem as fs
from ..util import tty
from ..util.compression import compress_file
from ..util.environ import tmp_environ
from ..util.executable import Executable
from ..util.filesystem import mkdirp
from ..util.filesystem import working_dir
from ..util.hash import hashit
from ..util.tty.color import colorize
from .enums import Result
from .enums import Skip


def stringify(arg: Any) -> str:
    if isinstance(arg, float) and arg > 1e5:
        return f"{arg:e}"
    return str(arg)


class TestCase:
    def __init__(
        self,
        root: str,
        path: str,
        *,
        analyze: str = "",
        family: Optional[str] = None,
        keywords: list[str] = [],
        parameters: dict[str, object] = {},
        timeout: Union[None, int] = None,
        runtime: Union[None, float, int] = None,
        skip: Skip = Skip(),
        baseline: list[tuple[str, str]] = [],
        sources: dict[str, list[tuple[str, str]]] = {},
    ):
        # file properties
        self.file_root = root
        self.file_path = path
        self.file = os.path.join(root, path)
        self.file_dir = os.path.dirname(self.file)
        assert os.path.exists(self.file)
        self.file_type = "vvt" if self.file.endswith(".vvt") else "pyt"

        # Other properties
        self.analyze = analyze
        self.keywords = keywords
        self.parameters = {} if parameters is None else dict(parameters)
        self._timeout = timeout
        self._runtime = runtime
        self.baseline = baseline
        self.sources = sources
        self._skip: Skip = skip
        # Environment variables specific to this case
        self.variables: dict[str, str] = {}

        # Name properties
        self.family = family or os.path.splitext(os.path.basename(self.file_path))[0]
        self.name = self.family
        self.display_name = self.family
        if self.parameters:
            keys = sorted(self.parameters.keys())
            s_vals = [stringify(self.parameters[k]) for k in keys]
            s_params = [f"{k}={s_vals[i]}" for (i, k) in enumerate(keys)]
            self.name = f"{self.name}.{'.'.join(s_params)}"
            self.display_name = f"{self.display_name}[{','.join(s_params)}]"
        self.fullname = os.path.join(os.path.dirname(self.file_path), self.name)
        self.id: str = hashit(self.fullname, length=20)

        # Execution properties
        self.cmd_line: str = ""
        self.exec_path = os.path.join(os.path.dirname(self.file_path), self.name)
        # Set during set up
        self.exec_root = None
        # The process running the test case
        self._process = None
        self.result: Result = Result("notrun")
        self.start: float = -1
        self.finish: float = -1
        self.returncode: int = -1

        # Dependency management
        self.dep_patterns: list[str] = []
        self.dependencies: list["TestCase"] = []
        self._depids: list[int] = []

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other) -> bool:
        if not isinstance(other, TestCase):
            raise ValueError(
                f"Cannot compare TestCase with type {other.__class__.__name__}"
            )
        return self.id == other.id

    def __str__(self) -> str:
        return self.display_name

    def __repr__(self) -> str:
        return self.display_name

    def pretty_repr(self) -> str:
        family = colorize("@*{%s}" % self.family)
        i = self.display_name.find("[")
        if i == -1:
            return family
        parts = self.display_name[i + 1 : -1].split(",")
        colors = itertools.cycle("bmgycr")
        for j, part in enumerate(parts):
            color = next(colors)
            parts[j] = colorize("@%s{%s}" % (color, part))
        return f"{family}[{','.join(parts)}]"

    def add_default_env(self, var: str, value: str) -> None:
        self.variables[var] = value

    def copy(self) -> "TestCase":
        return deepcopy(self)

    @property
    def logfile(self) -> str:
        return os.path.join(self.exec_dir, "nvtest-out.txt")

    @property
    def exec_dir(self) -> str:
        if self.exec_root is None:
            raise ValueError("Cannot call exec_dir until test case is setup")
        return os.path.join(self.exec_root, self.exec_path)

    @property
    def ready(self) -> bool:
        for dep in self.dependencies:
            if dep.result in (Result.SETUP, Result.NOTRUN, Result.NOTDONE):
                return False
        return True

    @property
    def size(self) -> int:
        return int(self.parameters.get("np") or 1)  # type: ignore

    @property
    def runtime(self) -> Union[float, int]:
        if self._runtime is None:
            return self.timeout
        return self._runtime

    @runtime.setter
    def runtime(self, arg: Union[None, int, float]):
        if arg is not None:
            assert isinstance(arg, (int, float))
            self._runtime = arg

    @property
    def timeout(self) -> int:
        if self._timeout is not None:
            return int(self._timeout)
        elif "fast" in self.keywords:
            return 5 * 30
        elif "long" in self.keywords:
            return 5 * 60 * 60
        else:
            return 60 * 60

    @property
    def skip(self):
        return self._skip

    @skip.setter
    def skip(self, arg: Union[str, bool, Skip]):
        if arg is False:
            self._skip.reason = ""
        elif arg is True:
            self._skip.reason = "Skip set to True"
        elif isinstance(arg, Skip):
            self._skip = arg
        else:
            self._skip.reason = arg

    def add_dependency(self, *cases: Union["TestCase", str]) -> None:
        for case in cases:
            if isinstance(case, TestCase):
                self.dependencies.append(case)
                self._depids.append(id(case))
            else:
                self.dep_patterns.append(case)

    @property
    def pythonpath(self):
        path = [_ for _ in os.getenv("PYTHONPATH", "").split(os.pathsep) if _.split()]
        if self.exec_dir not in path:
            path.insert(0, self.exec_dir)
        else:
            path.insert(0, path.pop(path.index(self.exec_dir)))
        return os.pathsep.join(path)

    def safe_substitute(self, string: str, **kwds: str) -> str:
        if "$" in string:
            t = Template(string)
            return t.safe_substitute(**kwds)
        return string.format(**kwds)

    def copy_sources_to_workdir(self, copy_all_resources: bool = False):
        workdir = self.exec_dir
        for action in ("copy", "link"):
            for t, dst in self.sources.get(action, []):
                if os.path.exists(t):
                    src = t
                else:
                    src = os.path.join(self.file_dir, t)
                dst = os.path.join(workdir, os.path.basename(dst))
                if not os.path.exists(src):
                    s = f"{action} resource file {t} not found"
                    tty.error(s)
                    self._skip.reason = s
                    continue
                elif os.path.exists(dst):
                    tty.warn(f"{os.path.basename(dst)} already exists in {workdir}")
                    continue
                if action == "copy" or copy_all_resources:
                    fs.force_copy(src, dst, echo=True)
                else:
                    relsrc = os.path.relpath(src, workdir)
                    fs.force_symlink(relsrc, dst, echo=True)

    def asdict(self):
        data = dict(vars(self))
        data["result"] = [data["result"].name, data["result"].reason]
        data["_skip"] = data["_skip"].reason
        for attr in ("file", "_depids", "dep_patterns"):
            data.pop(attr)
        dependencies = list(data.pop("dependencies"))
        data["dependencies"] = []
        for dependency in dependencies:
            data["dependencies"].append(dependency.asdict())
        return data

    @classmethod
    def load(
        cls,
        arg_path: Optional[str] = None,
        cases: Optional[list["TestCase"]] = None,
    ) -> "TestCase":
        """Load a test case from its json dump

        Parameters
        ----------
        arg_path : str, default ``os.getcwd()``
            The path to where the test was executed (or setup)
        cases : list[Test], default ``[]``
            Other test cases in this session.  If given, it is used to find
            dependencies, rather than loading dependencies

        Returns
        -------
        TestCase

        """
        path: str = arg_path or "."
        if path.endswith((".pyt", ".vvt")):
            path = os.path.dirname(path)
        elif path.endswith(".nvtest/case.json"):
            path = os.path.dirname(os.path.dirname(path))
        file = os.path.join(path, ".nvtest/case.json")
        if not os.path.exists(file):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file)
        with open(file) as fh:
            kwds = json.load(fh)
        dependencies = kwds.pop("dependencies")
        other_cases: list["TestCase"] = cases or []
        ids_of_other_cases = [case.id for case in other_cases]
        self = cls.from_dict(kwds)
        for dep in dependencies:
            if dep["id"] in ids_of_other_cases:
                tc = other_cases[ids_of_other_cases.index(dep["id"])]
            else:
                dir = str(self.exec_root)
                dep_file = os.path.join(dir, self.exec_path, ".nvtest", "case.json")
                tc = cls.load(dep_file)
            self.add_dependency(tc)
        return self

    def dump(self) -> None:
        dest = os.path.join(self.exec_dir, ".nvtest")
        mkdirp(dest)
        with working_dir(dest):
            with open("case.json", "w") as fh:
                json.dump(self.asdict(), fh, indent=2)
            with open("environment.json", "w") as fh:
                json.dump({"PYTHONPATH": self.pythonpath}, fh, indent=2)

    def rc_environ(self) -> dict[str, str]:
        env = {}
        f = os.path.join(self.exec_dir, ".nvtest/environment.json")
        if os.path.exists(f):
            with open(f) as fh:
                env.update(json.load(fh))
        return env

    @classmethod
    def from_dict(cls, kwds) -> "TestCase":
        self = cls(
            kwds.pop("file_root"),
            kwds.pop("file_path"),
            analyze=kwds.pop("analyze"),
            family=kwds.pop("family"),
            keywords=kwds.pop("keywords"),
            parameters=kwds.pop("parameters"),
            timeout=kwds.pop("_timeout"),
            runtime=kwds.pop("_runtime"),
            skip=Skip(kwds.pop("_skip") or None),
            baseline=kwds.pop("baseline"),
            sources=kwds.pop("sources"),
        )
        kwds.pop("fullname", None)
        result, reason = kwds.pop("result")
        self.result = Result(result, reason=reason)
        for dep in kwds.pop("dependencies", []):
            self.add_dependency(TestCase.from_dict(dep))
        for key, val in kwds.items():
            setattr(self, key, val)
        return self

    def to_json(self):
        data = self.asdict()
        done = self.result not in (Result.NOTRUN, Result.SKIP, Result.NOTDONE)
        if self.logfile and done:
            data["log"] = self.compressed_log()
        return json.dumps(data)

    def compressed_log(self) -> str:
        done = self.result not in (Result.NOTRUN, Result.SKIP, Result.NOTDONE)
        if self.logfile and done:
            kb_to_keep = 2 if self.result == Result.PASS else 300
            compressed_log = compress_file(self.logfile, kb_to_keep)
            return compressed_log
        return "Log not found"

    def setup(
        self,
        exec_root: Optional[str] = None,
        copy_all_resources: bool = False,
    ) -> None:
        tty.verbose(f"Setting up {self}")
        self.exec_root = exec_root or os.getcwd()  # type: ignore
        fs.force_remove(self.exec_dir)
        with fs.working_dir(self.exec_dir, create=True):
            with tty.log_output(self.logfile, mode="w"):
                if self.file_type == "vvt":
                    fs.force_symlink(self.logfile, "execute.log")
                with tty.timestamps():
                    tty.info(f"Preparing test: {self.name}")
                    tty.info(f"Directory: {os.getcwd()}")
                    tty.info("\nCleaning work directory...")
                    tty.info("\nLinking and copying working files...")
                    if copy_all_resources:
                        fs.force_copy(self.file, os.path.basename(self.file), echo=True)
                    else:
                        relsrc = os.path.relpath(self.file, os.getcwd())
                        fs.force_symlink(relsrc, os.path.basename(self.file), echo=True)
                    self.copy_sources_to_workdir(copy_all_resources=copy_all_resources)
                    if self.file_type == "vvt":
                        write_vvtest_util(self)
                    self.dump()
        tty.verbose(f"Done setting up {self}")
        return

    def update(self, attrs: dict[str, object]) -> None:
        for key, val in attrs.items():
            if key == "result":
                assert isinstance(val, Result)
            elif key == "skip":
                assert isinstance(val, Skip)
            setattr(self, key, val)

    def register_proc(self, proc) -> None:
        self._process = proc

    def run(self, log_level: Optional[int] = None) -> None:
        if self.dep_patterns:
            raise RuntimeError("Dependency patterns must be resolved before running")
        if log_level is not None:
            _log_level = tty.set_log_level(log_level)
        tty.info(f"STARTING: {self.pretty_repr()}", prefix=None)
        self.start = time.time()
        python = Executable(sys.executable)
        python.add_begin_callback(self.register_proc)
        with fs.working_dir(self.exec_dir):
            with tty.log_output(self.logfile, mode="a"):
                with tty.timestamps():
                    if self.analyze and self.analyze.startswith("-"):
                        args = [os.path.basename(self.file), self.analyze]
                    elif self.analyze:
                        args = [self.analyze]
                    else:
                        args = [os.path.basename(self.file)]
                    with tmp_environ(PYTHONPATH=self.pythonpath, **self.variables):
                        python(*args, fail_on_error=False, timeout=self.timeout)
                    self._process = None
                    self.cmd_line = python.cmd_line
                    rc = python.returncode
                    self.returncode = rc
                    self.result = Result.from_returncode(rc)
                    if self.result == Result.SKIP:
                        self._skip.reason = "runtime exception"
        self.finish = time.time()
        stat = self.result.cname
        tty.info(f"FINISHED: {self.pretty_repr()} {stat}", prefix=None)
        self.dump()
        if log_level is not None:
            tty.set_log_level(_log_level)
        return

    def kill(self):
        if self._process is not None:
            self._process.kill()
        self.result = Result("FAIL", "Process killed")

    def teardown(self) -> None:
        ...
