import errno
import glob
import itertools
import json
import os
import sys
import time
from contextlib import contextmanager
from copy import deepcopy
from string import Template
from typing import Optional
from typing import Union

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


@contextmanager
def null_context():
    yield


class TestCase:
    _logfile_name = "nvtest-out.txt"

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
        self.root = root
        self.path = path
        self.file = os.path.join(root, path)
        assert os.path.exists(self.file)
        self.family = family or os.path.splitext(os.path.basename(path))[0]
        self.analyze = analyze
        self.keywords = keywords
        self.parameters = {} if parameters is None else dict(parameters)
        self._timeout = timeout
        self._runtime = runtime
        self.baseline = baseline
        self.sources = sources
        self.dirname = os.path.dirname(self.file)
        self._process = None
        self.exec_root = None

        self.result: Result = Result("notrun")
        self.start: float = -1
        self.finish: float = -1
        self.id: str = hashit(os.path.join(self.root, self.fullname), length=20)
        self._skip: Skip = skip
        self.cmd_line: str = ""
        self.returncode: int = -1
        self.variables: dict[str, str] = {}

        self._dependencies: set[Union["TestCase", str]] = set()

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other) -> bool:
        if not isinstance(other, TestCase):
            raise ValueError(
                f"Cannot compare TestCase with type {other.__class__.__name__}"
            )
        return self.id == other.id

    def __str__(self) -> str:
        string = self.family
        id = self.identifier(sep=",")
        if id:
            string += f"[{id}]"
        return string

    def __repr__(self) -> str:
        return str(self)

    def pretty_repr(self) -> str:
        pretty = self.family
        id = self.identifier(sep=",")
        if id:
            parts = id.split(",")
            colors = itertools.cycle("bmgycr")
            for (i, part) in enumerate(parts):
                color = next(colors)
                parts[i] = colorize("@%s{%s}" % (color, part))
            pretty = f"{pretty}[{','.join(parts)}]"
        return pretty

    def add_default_env(self, var: str, value: str) -> None:
        self.variables[var] = value

    def copy(self) -> "TestCase":
        return deepcopy(self)

    @property
    def logfile(self) -> str:
        return os.path.join(self.exec_dir, self._logfile_name)

    @property
    def exec_dir(self) -> str:
        if self.exec_root is None:
            raise ValueError("Cannot call exec_dir until test case is setup")
        return os.path.join(self.exec_root, self.id)

    @property
    def type(self) -> str:
        return "vvt" if self.file.endswith(".vvt") else "pyt"

    @property
    def ready(self) -> bool:
        if any(not dep.ready for dep in self.dependencies if isinstance(dep, TestCase)):
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
    def skip(self, arg: Union[str, bool]):
        if arg is False:
            self._skip.reason = ""
        elif arg is True:
            self._skip.reason = "Skip set to True"
        else:
            self._skip.reason = arg

    def add_dependency(self, *cases: Union["TestCase", str]) -> None:
        for case in cases:
            self._dependencies.add(case)

    @property
    def dependencies(self) -> set["TestCase"]:
        return self._dependencies  # type: ignore

    def identifier(self, sep: str = ",") -> str:
        if not self.parameters:
            return ""
        keys = sorted(self.parameters.keys())
        return sep.join(f"{k}={self.parameters[k]}" for k in keys)

    @property
    def name(self) -> str:
        name = self.family
        id = self.identifier(sep=".")
        if id:
            name += f".{id}"
        return name

    @property
    def fullname(self) -> str:
        return os.path.join(os.path.dirname(self.path), self.name)

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
        for action in ("copy", "link"):
            for (t, dst) in self.sources.get(action, []):
                src = t if os.path.exists(t) else os.path.join(self.dirname, t)
                if not os.path.exists(src):
                    s = f"{action} resource file {t} not found"
                    tty.error(s)
                    self._skip.reason = s
                elif action == "copy" or copy_all_resources:
                    fs.force_copy(src, dst, echo=True)
                else:
                    relsrc = os.path.relpath(src, os.getcwd())
                    fs.force_symlink(relsrc, dst, echo=True)

    def asdict(self):
        data = dict(vars(self))
        data["result"] = [data["result"].name, data["result"].reason]
        data["_skip"] = data["_skip"].reason
        data.pop("file")
        dependencies = list(data.pop("_dependencies"))
        data["_dependencies"] = []
        for dependency in dependencies:
            data["_dependencies"].append(dependency.asdict())
        data["fullname"] = self.fullname
        return data

    @classmethod
    def load(cls, arg_path: Optional[str] = None) -> "TestCase":
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
        dependencies = kwds.pop("_dependencies")
        self = cls.from_dict(kwds)
        for dep in dependencies:
            dir = str(self.exec_root)
            dep_file = os.path.join(dir, dep["fullname"], ".nvtest", "case.json")
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
            kwds.pop("root"),
            kwds.pop("path"),
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
        for dep in kwds.pop("_dependencies", []):
            self.add_dependency(TestCase.from_dict(dep))
        for (key, val) in kwds.items():
            setattr(self, key, val)
        return self

    def to_json(self):
        data = self.asdict()
        done = self.result not in (Result.NOTRUN, Result.SKIP, Result.NOTDONE)
        if self.logfile and done:
            kb_to_keep = 2 if self.result == Result.PASS else 300
            compressed_log = compress_file(self.logfile, kb_to_keep)
            data["log"] = compressed_log
        return json.dumps(data)

    def setup(
        self,
        exec_root: Optional[str] = None,
        copy_all_resources: bool = False,
    ) -> None:
        tty.verbose(f"Setting up {self}")
        self.exec_root = exec_root or os.getcwd()  # type: ignore
        fs.force_remove(self.exec_dir)
        _timestamp_stat = tty.set_timestamp_stat(True)
        with fs.working_dir(self.exec_dir, create=True):
            with tty.log_output(self.logfile, mode="w"):
                tty.info(f"Preparing test: {self.name}")
                tty.info(f"Directory: {os.getcwd()}")
                tty.info("\nCleaning work directory...")
                for item in glob.glob("*"):
                    fs.force_remove(item)
                tty.info("\nLinking and copying working files...")
                if copy_all_resources:
                    fs.force_copy(self.file, os.path.basename(self.file), echo=True)
                else:
                    relsrc = os.path.relpath(self.file, os.getcwd())
                    fs.force_symlink(relsrc, os.path.basename(self.file), echo=True)
                self.copy_sources_to_workdir(copy_all_resources=copy_all_resources)
                if self.type == "vvt":
                    self.write_vvtest_util()
                self.dump()
        tty.set_timestamp_stat(_timestamp_stat)
        tty.verbose(f"Done setting up {self}")
        return

    def update(self, attrs: dict[str, object]) -> None:
        for (key, val) in attrs.items():
            if key == "result":
                assert isinstance(val, Result)
            elif key == "skip":
                assert isinstance(val, Skip)
            setattr(self, key, val)

    def register_proc(self, proc) -> None:
        self._process = proc

    def run(self, log_level: Optional[int] = None) -> None:
        if log_level is not None:
            _log_level = tty.set_log_level(log_level)
        tty.info(f"STARTING: {self.pretty_repr()}", prefix="")
        self.start = time.time()
        python = Executable(sys.executable)
        python.add_begin_callback(self.register_proc)
        _timestamp_stat = tty.set_timestamp_stat(True)
        with fs.working_dir(self.exec_dir):
            with tty.log_output(self.logfile, mode="a"):
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
        tty.set_timestamp_stat(_timestamp_stat)
        self.finish = time.time()
        stat = self.result.cname
        tty.info(f"FINISHED: {self.pretty_repr()} {stat}", prefix="")
        self.dump()
        if log_level is not None:
            tty.set_log_level(_log_level)
        return

    def kill(self):
        if self._process is not None:
            self._process.kill()
        self.result = Result("FAIL", "Process killed")

    def write_vvtest_util(self):
        with open("vvtest_util.py", "w") as fh:
            fh.write(f"NAME = {self.family!r}\n")
            fh.write(f"TESTID = {self.fullname!r}\n")
            fh.write(f"PLATFORM = {sys.platform.lower()!r}\n")
            fh.write(f"SRCDIR = {self.dirname!r}\n")
            fh.write(f"TIMEOUT = {self.timeout!r}\n")
            fh.write("PROJECT = ''\n")
            fh.write("diff_exit_status = 64\n")
            fh.write("skip_exit_status = 63\n")
            for (key, val) in self.parameters.items():
                fh.write(f"{key} = {val!r}\n")
            fh.write("PARAM_DICT = {\n")
            for (key, val) in self.parameters.items():
                fh.write(f"    {key!r}: {val!r},\n")
            fh.write("}\n")

    def teardown(self) -> None:
        pass
