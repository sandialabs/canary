import itertools
import json
import os
import re
import sys
import time
from copy import deepcopy
from string import Template
from typing import Any
from typing import Optional
from typing import Union

from .. import config
from ..compat.vvtest import write_vvtest_util
from ..util import filesystem as fs
from ..util import tty
from ..util.compression import compress_file
from ..util.environ import tmp_environ
from ..util.executable import Executable
from ..util.filesystem import copyfile
from ..util.filesystem import mkdirp
from ..util.filesystem import working_dir
from ..util.hash import hashit
from ..util.tty.color import colorize
from .status import Status


def stringify(arg: Any) -> str:
    if isinstance(arg, float):
        return f"{arg:g}"
    elif isinstance(arg, int):
        return f"{arg:d}"
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
        timeout: Optional[int] = None,
        runtime: Union[None, float, int] = None,
        baseline: list[Union[str, tuple[str, str]]] = [],
        sources: dict[str, list[tuple[str, str]]] = {},
    ):
        # file properties
        self.file_root = root
        self.file_path = path
        self.file = os.path.join(root, path)
        self.file_dir = os.path.dirname(self.file)
        assert os.path.exists(self.file)
        self.file_type = "vvt" if self.file.endswith(".vvt") else "pyt"
        self._active: Optional[bool] = None

        # Other properties
        self.analyze = analyze
        self._keywords = keywords
        self.parameters = {} if parameters is None else dict(parameters)
        self._timeout = timeout
        self._runtime = runtime
        self.baseline = baseline
        self.sources = sources
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
        self.status = Status()
        self._mask: str = ""

        self.cmd_line: str = ""
        self.exec_root: Optional[str] = None
        self.exec_path = os.path.join(os.path.dirname(self.file_path), self.name)
        # The process running the test case
        self._process = None
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

    def matches(self, pattern) -> bool:
        if pattern.startswith("/") and self.id.startswith(pattern[1:]):
            return True
        elif self.display_name == pattern:
            return True
        elif self.file_path.endswith(pattern):
            return True
        return False

    @property
    def masked(self) -> bool:
        return bool(self.mask)

    @property
    def skipped(self) -> bool:
        return self.status == "skipped"

    @property
    def mask(self) -> str:
        return self._mask

    @mask.setter
    def mask(self, arg: str) -> None:
        self._mask = " ".join(arg.split())

    def unmask(self) -> None:
        self._mask = ""

    @staticmethod
    def spec_like(spec: str) -> bool:
        display_name_pattern = r"^[a-zA-Z_]\w*\[.*\]$"
        if spec.startswith("/") and not os.path.exists(spec):
            return True
        elif re.search(display_name_pattern, spec):
            return True
        return False

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

    def keywords(self, implicit: bool = False) -> list[str]:
        kwds = {kw for kw in self._keywords}
        if implicit:
            kwds.add(self.status.name.lower())
            kwds.add(self.name)
            kwds.add(self.family)
            kwds.update(self.parameters.keys())
        return list(kwds)

    def set_attribute(self, name: str, value: Any) -> None:
        if name in self.__dict__:
            raise KeyError(f"{name} is already an attribute of {self}")
        setattr(self, name, value)

    def add_default_env(self, var: str, value: str) -> None:
        self.variables[var] = value

    def copy(self) -> "TestCase":
        return deepcopy(self)

    @property
    def active(self) -> bool:
        return self._active or False

    @active.setter
    def active(self, arg: bool) -> None:
        self._active = bool(arg)

    @property
    def duration(self):
        if self.start == -1 or self.finish == -1:
            return -1
        return self.finish - self.start

    def logfile(self, stage: Optional[str] = None) -> str:
        if stage is None:
            return os.path.join(self.exec_dir, "nvtest-out.txt")
        return os.path.join(self.exec_dir, f"nvtest-{stage}-out.txt")

    @property
    def exec_dir(self) -> str:
        exec_root = self.exec_root
        if not exec_root:
            exec_root = config.get("session:work_tree")
        if not exec_root:
            raise ValueError("exec_root must be set during set up") from None
        return os.path.normpath(os.path.join(exec_root, self.exec_path))

    def ready(self) -> int:
        """Return whether this case is ready to run or not

        If the return value is 1, it is ready
        If the return value is 0, it is not ready
        If the return value is -1, it will never by ready

        """
        if not self.dependencies:
            return 1
        stat = [dep.status.value for dep in self.dependencies]
        if all([_ in ("success", "diffed", "failed", "timeout") for _ in stat]):
            return 1
        for dep in self.dependencies:
            if dep.status == "skipped":
                return -1
        return 0

    @property
    def processors(self) -> int:
        return int(self.parameters.get("np") or 1)  # type: ignore

    @property
    def devices(self) -> int:
        return int(self.parameters.get("ndevice") or 0)  # type: ignore

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
        elif "fast" in self._keywords:
            return 5 * 30
        elif "long" in self._keywords:
            return 5 * 60 * 60
        else:
            return 60 * 60

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
                    s = f"{self}: {action} resource file {t} not found"
                    raise MissingSourceError(s)
                elif os.path.exists(dst):
                    tty.warn(f"{os.path.basename(dst)} already exists in {workdir}")
                    continue
                if action == "copy" or copy_all_resources:
                    fs.force_copy(src, dst, echo=tty.info)
                else:
                    relsrc = os.path.relpath(src, workdir)
                    fs.force_symlink(relsrc, dst, echo=tty.info)

    def asdict(self, *keys):
        data = dict(vars(self))
        data["status"] = [data["status"].value, data["status"].details]
        for attr in ("file", "_depids", "dep_patterns"):
            data.pop(attr)
        dependencies = list(data.pop("dependencies"))
        data["dependencies"] = []
        for dependency in dependencies:
            data["dependencies"].append(dependency.asdict())
        if not keys:
            return data
        return {key: data[key] for key in keys}

    def dump(self) -> None:
        dest = os.path.join(self.exec_dir, ".nvtest")
        mkdirp(dest)
        with working_dir(dest):
            with open("case.json", "w") as fh:
                json.dump(self.asdict(), fh, indent=2)
            with open("environment.json", "w") as fh:
                json.dump({"PYTHONPATH": self.pythonpath}, fh, indent=2)

    def load_results(self):
        file = os.path.join(self.exec_dir, ".nvtest/case.json")
        if not os.path.exists(file):
            raise FileNotFoundError(file)
        with open(file) as fh:
            return json.load(fh)

    def rc_environ(self) -> dict[str, str]:
        env = dict(PYTHONPATH=self.pythonpath)
        env.update(self.variables)
        return env

    @classmethod
    def from_dict(cls, kwds) -> "TestCase":
        self = cls(
            kwds.pop("file_root"),
            kwds.pop("file_path"),
            analyze=kwds.pop("analyze"),
            family=kwds.pop("family"),
            keywords=kwds.pop("_keywords"),
            parameters=kwds.pop("parameters"),
            timeout=kwds.pop("_timeout"),
            runtime=kwds.pop("_runtime"),
            baseline=kwds.pop("baseline"),
            sources=kwds.pop("sources"),
        )
        kwds.pop("fullname", None)
        status, details = kwds.pop("status")
        self.status = Status(status, details=details)
        self.returncode = kwds.pop("returncode")
        mask = kwds.pop("mask", "")
        if mask:
            self.mask = mask
        for dep in kwds.pop("dependencies", []):
            self.add_dependency(TestCase.from_dict(dep))
        for key, val in kwds.items():
            setattr(self, key, val)
        return self

    def to_json(self):
        data = self.asdict()
        done = self.status.value in ("failed", "success")
        if done:
            data["log"] = self.compressed_log()
        return json.dumps(data)

    def compressed_log(self) -> str:
        done = self.status.value in ("failed", "success")
        if done:
            kb_to_keep = 2 if self.status == "success" else 300
            compressed_log = compress_file(self.logfile(), kb_to_keep)
            return compressed_log
        return "Log not found"

    def setup(self, exec_root: str, copy_all_resources: bool = False) -> None:
        tty.verbose(f"Setting up {self}")
        if self.exec_root is not None:
            assert os.path.samefile(exec_root, self.exec_root)
        self.exec_root = exec_root
        if os.path.exists(self.exec_dir):
            with fs.working_dir(self.exec_dir):
                for f in os.listdir("."):
                    fs.force_remove(f)
        with fs.working_dir(self.exec_dir, create=True):
            self.setup_exec_dir(copy_all_resources=copy_all_resources)
            self.status.set("staged")
            self.dump()
        tty.verbose(f"Done setting up {self}")

    def setup_exec_dir(self, copy_all_resources: bool = False) -> None:
        with tty.log_output(self.logfile("setup"), mode="w"):
            with tty.timestamps():
                tty.info(f"Preparing test: {self.name}")
                tty.info(f"Directory: {os.getcwd()}")
                tty.info("Cleaning work directory...")
                tty.info("Linking and copying working files...")
                if copy_all_resources:
                    fs.force_copy(self.file, os.path.basename(self.file), echo=tty.info)
                else:
                    relsrc = os.path.relpath(self.file, os.getcwd())
                    fs.force_symlink(relsrc, os.path.basename(self.file), echo=tty.info)
                self.copy_sources_to_workdir(copy_all_resources=copy_all_resources)

    def update(self, attrs: dict[str, object]) -> None:
        for key, val in attrs.items():
            if key == "status":
                if isinstance(val, (tuple, list)):
                    assert len(val) == 2
                    val = Status(val[0], val[1])
                assert isinstance(val, Status)
            setattr(self, key, val)

    def register_proc(self, proc) -> None:
        self._process = proc

    def do_baseline(self) -> None:
        if not self.baseline:
            return
        tty.info(f"Rebaselining {self.pretty_repr()}")
        with fs.working_dir(self.exec_dir):
            if self.file_type == "vvt":
                write_vvtest_util(self, baseline=True)
            for arg in self.baseline:
                if isinstance(arg, tuple):
                    a, b = arg
                    src = os.path.join(self.exec_dir, a)
                    dst = os.path.join(self.file_dir, b)
                    if os.path.exists(src):
                        tty.print(f"    Replacing {b} with {a}")
                        copyfile(src, dst)
                else:
                    python = Executable(sys.executable)
                    args = [os.path.basename(self.file), self.baseline]
                    python(*args, fail_on_error=False)

    def run(self, **kwds: Any) -> None:
        if os.getenv("NVTEST_RESETUP"):
            assert isinstance(self.exec_root, str)
            self.setup(self.exec_root)
        if self.dep_patterns:
            raise RuntimeError("Dependency patterns must be resolved before running")
        id = colorize("@b{%s}" % self.id[:7])
        fmt = "{{0}}: {0} {1} {{1}}".format(id, self.pretty_repr())
        try:
            self.start = time.time()
            tty.info(fmt.format("STARTING", ""), prefix=None)
            self._run(**kwds)
        except Exception:
            self.returncode = 1
            self.status.set("failed", "unknown failure")
            raise
        finally:
            with open(self.logfile(), "w") as fh:
                for stage in ("setup", "test"):
                    file = self.logfile(stage)
                    if os.path.exists(file):
                        fh.write(open(file).read())
            if self.file_type == "vvt":
                fs.force_symlink(self.logfile(), "execute.log")
            self.finish = time.time()
            tty.info(fmt.format("FINISHED", self.status.cname), prefix=None)
            self.dump()
        return

    def _run(self, **kwds: Any) -> None:
        python = Executable(sys.executable)
        python.add_begin_callback(self.register_proc)
        with fs.working_dir(self.exec_dir):
            if self.file_type == "vvt":
                write_vvtest_util(self)
            with tty.log_output(self.logfile("test"), mode="w"):
                with tty.timestamps():
                    args = self.command_line_args(**kwds)
                    env = self.rc_environ()
                    tty.info(f"Running {self.display_name}")
                    tty.info(f"Command line: {sys.executable} {' '.join(args)}")
                    with tmp_environ(**env):
                        python(*args, fail_on_error=False, timeout=self.timeout)
                    self._process = None
                    self.cmd_line = python.cmd_line
                    rc = python.returncode
                    self.returncode = rc
                    self.status = Status.from_returncode(rc)
        return

    @staticmethod
    def kwds_to_command_line_args(**kwds: Any) -> list[str]:
        args: list = []
        for key, val in kwds.items():
            prefix = "-" if len(key) == 1 else "--"
            opt = f"{prefix}{key.replace('_', '-')}"
            if val is False:
                continue
            elif val is True:
                args.append(opt)
            elif len(key) == 1:
                args.append(f"{opt}{val}")
            else:
                args.append(f"{opt}={val}")
        return args

    def command_line_args(self, **kwds: Any) -> list[str]:
        if self.analyze:
            if self.analyze.startswith("-"):
                args = [os.path.basename(self.file), self.analyze]
            else:
                args = [self.analyze]
        else:
            args = [os.path.basename(self.file)]
            extra_args = self.kwds_to_command_line_args(**kwds)
            args.extend(extra_args)
        return args

    def kill(self):
        if self._process is not None:
            self._process.kill()
        self.status = Status("failed", "fail")  # "Process killed")

    def teardown(self) -> None:
        ...


class MissingSourceError(Exception):
    pass
