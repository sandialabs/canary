import datetime
import io
import itertools
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from copy import deepcopy
from typing import IO
from typing import Any
from typing import Generator
from typing import Optional
from typing import Type
from typing import Union

from .. import config
from .. import plugin
from ..error import diff_exit_status
from ..paramset import ParameterSet
from ..third_party.color import colorize
from ..util import cache
from ..util import filesystem as fs
from ..util import logging
from ..util.compression import compress_str
from ..util.executable import Executable
from ..util.filesystem import copyfile
from ..util.filesystem import mkdirp
from ..util.hash import hashit
from ..util.time import timestamp
from .runner import Runner
from .status import Status


def stringify(arg: Any, float_fmt: Optional[str] = None) -> str:
    if isinstance(arg, float) and float_fmt is not None:
        return float_fmt % arg
    if hasattr(arg, "string"):
        return arg.string
    elif isinstance(arg, float):
        return f"{arg:g}"
    elif isinstance(arg, int):
        return f"{arg:d}"
    return str(arg)


class TestCase(Runner):
    _dbfile = "testcase.lock"

    REGISTRY: set[Type["TestCase"]] = set()

    def __init_subclass__(cls, **kwargs):
        cls.REGISTRY.add(cls)
        return super().__init_subclass__(**kwargs)

    def __init__(
        self,
        file_root: Optional[str] = None,
        file_path: Optional[str] = None,
        *,
        family: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
        baseline: Optional[list[Union[str, tuple[str, str]]]] = None,
        sources: Optional[dict[str, list[tuple[str, str]]]] = None,
        xstatus: Optional[int] = None,
        preload: Optional[str] = None,
    ):
        super().__init__()

        # We need to be able to dump the test case to a json file and then reload it.  To do so, we
        # initialize all attributes as private and employ getters/setters
        self._file_root: str = ""
        self._file_path: str = ""
        self._url: Optional[str] = None
        self._family: str = ""
        self._keywords: list[str] = []
        self._parameters: dict[str, Any] = {}
        self._timeout: Optional[float] = None
        self._baseline: list[Union[str, tuple[str, str]]] = []
        self._sources: dict[str, list[tuple[str, str]]] = {}
        self._xstatus: int = 0
        self._preload: Optional[str] = None

        if file_root is not None:
            self.file_root = file_root
        if file_path is not None:
            self.file_path = file_path
        if family is not None:
            self.family = family
        if keywords is not None:
            self.keywords = keywords
        if parameters is not None:
            self.parameters = parameters
        if timeout is not None:
            self.timeout = timeout
        if baseline is not None:
            self.baseline = baseline
        if sources is not None:
            self.sources = sources
        if xstatus is not None:
            self.xstatus = xstatus
        if preload is not None:
            self.preload = preload

        self._mask: Optional[str] = None
        self._name: Optional[str] = None
        self._display_name: Optional[str] = None
        self._classname: Optional[str] = None
        self._id: Optional[str] = None
        self._status: Status = Status()
        self._cmd_line: Optional[str] = None
        self._exec_root: Optional[str] = None

        # The process running the test case
        self._start: float = -1.0
        self._finish: float = -1.0
        self._returncode: int = -1

        # Dependency management
        self._dep_patterns: list[str] = []
        self._dependencies: list["TestCase"] = []

        # mean, min, max runtimes
        self._runtimes: list[Optional[float]] = [None, None, None]

        self._launcher: Optional[str] = None
        self._preflags: Optional[list[str]] = None
        self._command: Optional[str] = None
        self._postflags: Optional[list[str]] = None

        # Environment variables specific to this case
        self._variables: dict[str, str] = {}

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other) -> bool:
        if not isinstance(other, TestCase):
            raise ValueError(f"Cannot compare TestCase with type {other.__class__.__name__}")
        return self.id == other.id

    def __str__(self) -> str:
        return self.display_name

    def __repr__(self) -> str:
        return self.display_name

    @property
    def dbfile(self) -> str:
        file = os.path.join(self.exec_dir, self._dbfile)
        return file

    @property
    def file_root(self) -> str:
        assert self._file_root is not None
        return self._file_root

    @file_root.setter
    def file_root(self, arg: str) -> None:
        assert os.path.exists(arg)
        self._file_root = arg

    @property
    def file_path(self) -> str:
        assert self._file_path is not None
        return self._file_path

    @file_path.setter
    def file_path(self, arg: str) -> None:
        assert os.path.exists(os.path.join(self.file_root, arg))
        self._file_path = arg

    @property
    def file(self) -> str:
        return os.path.join(self.file_root, self.file_path)

    @property
    def file_dir(self) -> str:
        return os.path.dirname(self.file)

    @property
    def exec_root(self) -> Optional[str]:
        return self._exec_root

    @exec_root.setter
    def exec_root(self, arg: Optional[str]) -> None:
        if arg is not None:
            assert os.path.exists(arg)
            self._exec_root = arg

    @property
    def exec_path(self) -> str:
        return os.path.join(os.path.dirname(self.file_path), self.name)

    @property
    def exec_dir(self) -> str:
        exec_root = self.exec_root
        if not exec_root:
            exec_root = config.get("session:root")
        if not exec_root:
            raise ValueError("exec_root must be set during set up") from None
        return os.path.normpath(os.path.join(exec_root, self.exec_path))

    @property
    def family(self) -> str:
        if not self._family:
            self._family = os.path.splitext(os.path.basename(self.file_path))[0]
        return self._family

    @family.setter
    def family(self, arg: str) -> None:
        self._family = arg

    @property
    def keywords(self) -> list[str]:
        return self._keywords

    @keywords.setter
    def keywords(self, arg: list[str]) -> None:
        self._keywords = list(arg)

    @property
    def implicit_keywords(self) -> list[str]:
        kwds = {self.status.name.lower(), self.status.value.lower(), self.name, self.family}
        return list(kwds)

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    @parameters.setter
    def parameters(self, arg: dict[str, Any]) -> None:
        self._parameters = dict(arg)

    @property
    def dep_patterns(self) -> list[str]:
        return self._dep_patterns

    @dep_patterns.setter
    def dep_patterns(self, arg: list[str]) -> None:
        self._dep_patterns = list(arg)

    @property
    def dependencies(self) -> list["TestCase"]:
        return self._dependencies

    @dependencies.setter
    def dependencies(self, arg: list["TestCase"]) -> None:
        self._dependencies = arg

    @property
    def runtimes(self) -> list[Optional[float]]:
        if self._runtimes[0] is None:
            self.load_runtimes()
        return self._runtimes

    @runtimes.setter
    def runtimes(self, arg: list[Optional[float]]) -> None:
        self._runtimes = arg

    @property
    def timeout(self) -> float:
        if self._timeout is None:
            self.set_default_timeout()
        assert isinstance(self._timeout, float)
        return self._timeout

    @timeout.setter
    def timeout(self, arg: float) -> None:
        self._timeout = arg

    @property
    def baseline(self) -> list[Union[str, tuple[str, str]]]:
        return self._baseline

    @baseline.setter
    def baseline(self, arg: list[Union[str, tuple[str, str]]]) -> None:
        self._baseline = list(arg)

    @property
    def sources(self) -> dict[str, list[tuple[str, str]]]:
        return self._sources

    @sources.setter
    def sources(self, arg: dict[str, list[tuple[str, str]]]) -> None:
        self._sources = arg

    @property
    def xstatus(self) -> int:
        return self._xstatus

    @xstatus.setter
    def xstatus(self, arg: int) -> None:
        self._xstatus = arg

    @property
    def preload(self) -> Optional[str]:
        return self._preload

    @preload.setter
    def preload(self, arg: Optional[str]) -> None:
        self._preload = arg

    @property
    def skipped(self) -> bool:
        return self.status == "skipped"

    @property
    def status(self) -> Status:
        if self._status.pending():
            # Determine if dependent cases have completed and, if so, flip status to 'ready'
            if not self.dependencies:
                raise ValueError("should never have a pending case without dependencies")
            stat = [dep.status.value for dep in self.dependencies]
            if all([_ in ("success", "diffed") for _ in stat]):
                self._status.set("ready")
            elif any([_ == "skipped" for _ in stat]):
                self._status.set("skipped", "one or more dependency was skipped")
            elif any([_ == "cancelled" for _ in stat]):
                self._status.set("not_run", "one or more dependency was cancelled")
            elif any([_ == "timeout" for _ in stat]):
                self._status.set("not_run", "one or more dependency timed out")
            elif any([_ == "failed" for _ in stat]):
                self._status.set("not_run", "one or more dependency failed")
        return self._status

    @status.setter
    def status(self, arg: Union[Status, dict[str, str]]) -> None:
        if isinstance(arg, Status):
            self._status.set(arg.value, details=arg.details)
        elif isinstance(arg, dict):
            self._status.set(arg["value"], details=arg["details"])
        else:
            raise ValueError(arg)

    @property
    def url(self) -> Optional[str]:
        return self._url

    @url.setter
    def url(self, arg: str) -> None:
        self._url = arg

    @property
    def launcher(self) -> Optional[str]:
        return self._launcher

    @launcher.setter
    def launcher(self, arg: Optional[str]) -> None:
        self._launcher = arg

    @property
    def preflags(self) -> list[str]:
        return self._preflags or []

    @preflags.setter
    def preflags(self, arg: list[str]) -> None:
        self._preflags = arg

    @property
    def postflags(self) -> list[str]:
        return self._postflags or []

    @postflags.setter
    def postflags(self, arg: list[str]) -> None:
        self._postflags = arg

    @property
    def command(self) -> str:
        if self._command is None:
            self._command = os.path.basename(self.file)
        assert self._command is not None
        return self._command

    @command.setter
    def command(self, arg: str) -> None:
        self._command = arg

    @property
    def variables(self) -> dict[str, str]:
        return self._variables

    @variables.setter
    def variables(self, arg: dict[str, str]) -> None:
        self._variables = dict(arg)

    @property
    def mask(self) -> Optional[str]:
        return self._mask

    @mask.setter
    def mask(self, arg: str) -> None:
        self._mask = arg

    @property
    def name(self) -> str:
        if self._name is None:
            self.set_default_names()
        assert self._name is not None
        return self._name

    @name.setter
    def name(self, arg: str) -> None:
        self._name = arg

    @property
    def display_name(self) -> str:
        if self._display_name is None:
            self.set_default_names()
        assert self._display_name is not None
        return self._display_name

    @display_name.setter
    def display_name(self, arg: str) -> None:
        self._display_name = arg

    @property
    def fullname(self) -> str:
        return os.path.join(os.path.dirname(self.file_path), self.name)

    @property
    def classname(self) -> str:
        if self._classname is None:
            self.set_default_names()
        assert self._classname is not None
        return self._classname

    @classname.setter
    def classname(self, arg: str) -> None:
        self._classname = arg

    @property
    def cmd_line(self) -> Optional[str]:
        return self._cmd_line

    @cmd_line.setter
    def cmd_line(self, arg: str) -> None:
        self._cmd_line = arg

    @property
    def start(self) -> float:
        return self._start

    @start.setter
    def start(self, arg: float) -> None:
        self._start = arg

    @property
    def finish(self) -> float:
        return self._finish

    @finish.setter
    def finish(self, arg: float) -> None:
        self._finish = arg

    @property
    def duration(self):
        if self.start == -1 or self.finish == -1:
            return -1
        return self.finish - self.start

    @property
    def returncode(self) -> int:
        return self._returncode

    @returncode.setter
    def returncode(self, arg: int) -> None:
        self._returncode = int(arg)

    @property
    def id(self):
        if not self._id:
            unique_str = io.StringIO()
            unique_str.write(self.name)
            unique_str.write(f",{self.file_path}")
            for k in sorted(self.parameters):
                unique_str.write(f",{k}={stringify(self.parameters[k], float_fmt='%.16e')}")
            self._id = hashit(unique_str.getvalue(), length=20)
        return self._id

    @id.setter
    def id(self, arg: str) -> None:
        assert isinstance(arg, str)
        self._id = arg

    @property
    def cpus(self) -> int:
        return int(self.parameters.get("np") or 1)  # type: ignore

    @property
    def processors(self) -> int:
        return self.cpus

    @property
    def nodes(self) -> int:
        if "nnode" in self.parameters:
            return int(self.parameters["nnode"])  # type: ignore
        else:
            cores_per_socket = config.get("machine:cores_per_socket")
            sockets_per_node = config.get("machine:sockets_per_node") or 1
            cores_per_node = cores_per_socket * sockets_per_node
            return int(math.ceil(self.cpus / cores_per_node))

    @property
    def gpus(self) -> int:
        if "ngpu" in self.parameters:
            return int(self.parameters["ngpu"])  # type: ignore
        elif "ndevice" in self.parameters:
            return int(self.parameters["ndevice"])  # type: ignore
        else:
            return 0

    @property
    def cputime(self) -> Union[float, int]:
        return self.runtime * self.cpus

    @property
    def runtime(self) -> Union[float, int]:
        if self._runtimes[0] is None:
            return self.timeout
        return self._runtimes[0]

    @property
    def pythonpath(self):
        path = [_ for _ in os.getenv("PYTHONPATH", "").split(os.pathsep) if _.split()]
        if self.exec_dir not in path:
            path.insert(0, self.exec_dir)
        else:
            path.insert(0, path.pop(path.index(self.exec_dir)))
        return os.pathsep.join(path)

    def logfile(self, stage: Optional[str] = None) -> str:
        if stage is None:
            return os.path.join(self.exec_dir, "nvtest-out.txt")
        return os.path.join(self.exec_dir, f"nvtest-{stage}-out.txt")

    def set_default_names(self) -> None:
        self.name = self.family
        self.display_name = self.family
        if self.parameters:
            keys = sorted(self.parameters.keys())
            s_vals = [stringify(self.parameters[k]) for k in keys]
            s_params = [f"{k}={s_vals[i]}" for (i, k) in enumerate(keys)]
            self.name = f"{self._name}.{'.'.join(s_params)}"
            self.display_name = f"{self._display_name}[{','.join(s_params)}]"
        classname = os.path.dirname(self.file_path).strip()
        if not classname:
            classname = os.path.basename(self.file_dir).strip()
        self.classname = classname.replace(os.path.sep, ".")

    def set_default_timeout(self) -> None:
        if self.runtimes[2] is not None:
            max_runtime = self.runtimes[2]
            if max_runtime < 5.0:
                timeout = 120.0
            elif max_runtime < 120.0:
                timeout = 360.0
            elif max_runtime < 300.0:
                timeout = 900.0
            elif max_runtime < 600.0:
                timeout = 1800.0
            else:
                timeout = 2.0 * self.runtimes[2]
        elif "fast" in self.keywords:
            timeout = config.get("test:timeout:fast")
        elif "long" in self.keywords:
            timeout = config.get("test:timeout:long")
        else:
            timeout = config.get("test:timeout:default")
        self._timeout = timeout

    def load_runtimes(self):
        # return mean, min, max runtimes
        if config.get("config:no_cache"):
            return [None, None, None]
        cache_dir = cache.get_cache_dir(self.file_root)
        file = self.cache_file(cache_dir)
        if not os.path.exists(file):
            return [None, None, None]
        tries = 0
        while tries < 3:
            try:
                _, mean, minimum, maximum = json.load(open(file))
                return [mean, minimum, maximum]
            except json.decoder.JSONDecodeError:
                tries += 1
        return [None, None, None]

    def cache_file(self, path):
        return os.path.join(path, f"timing/{self.id[:2]}/{self.id[2:]}.json")

    def cache_runtime(self) -> None:
        """store mean, min, max runtimes"""
        if config.get("config:no_cache"):
            return
        if self.status.value not in ("success", "diffed"):
            return
        cache_dir = cache.create_cache_dir(self.file_root)
        if cache_dir is None:
            return
        file = self.cache_file(cache_dir)
        if not os.path.exists(file):
            n = 0
            mean = minimum = maximum = self.duration
        else:
            try:
                n, mean, minimum, maximum = json.load(open(file))
            except json.decoder.JSONDecodeError:
                n = 0
                mean = minimum = maximum = self.duration
            finally:
                mean = (self.duration + mean * n) / (n + 1)
                minimum = min(minimum, self.duration)
                maximum = max(maximum, self.duration)
        mkdirp(os.path.dirname(file))
        tries = 0
        while tries < 3:
            try:
                with open(file, "w") as fh:
                    json.dump([n + 1, mean, minimum, maximum], fh)
                break
            except Exception:
                tries += 1

    def set_attribute(self, name: str, value: Any) -> None:
        if name in self.__dict__:
            raise KeyError(f"{name} is already an attribute of {self}")
        setattr(self, name, value)

    def add_default_env(self, *args: dict[str, str], **kwds: str) -> None:
        if args:
            for arg in args:
                self.variables.update(arg)
        if kwds:
            self.variables.update(kwds)

    def update(self, **attrs: Any) -> None:
        """Restore values from a snapshot"""
        for name, value in attrs.items():
            if name == "id":
                if value != self.id:
                    raise ValueError("Incorrect case ID")
            elif name == "dependencies":
                for i, dep in enumerate(value):
                    if isinstance(dep, TestCase):
                        self.dependencies[i] = dep
            elif name == "cpu_ids":
                self._cpu_ids = value
            elif name == "gpu_ids":
                self._gpu_ids = value
            else:
                setattr(self, name, value)

    def describe(self, include_logfile_path: bool = False) -> str:
        """Write a string describing the test case"""
        id = colorize("@*b{%s}" % self.id[:7])
        if self.mask is not None:
            string = "@*c{EXCLUDED} %s %s: %s" % (id, self.pretty_repr(), self.mask)
            return colorize(string)
        string = "%s %s %s" % (self.status.cname, id, self.pretty_repr())
        if self.duration > 0:
            today = datetime.datetime.today()
            start = datetime.datetime.fromtimestamp(self.start)
            finish = datetime.datetime.fromtimestamp(self.finish)
            dt = today - start
            fmt = "%H:%m:%S" if dt.days <= 1 else "%M %d %H:%m:%S"
            a = start.strftime(fmt)
            b = finish.strftime(fmt)
            string += f" started: {a}, finished: {b}, duration: {self.duration:.2f}s."
        elif self.status == "skipped":
            string += ": Skipped due to %s" % self.status.details
        if include_logfile_path:
            f = os.path.relpath(self.logfile(), os.getcwd())
            string += colorize(": @m{%s}" % f)
        return string

    def complete(self) -> bool:
        return self.status.complete()

    def ready(self) -> bool:
        return self.status.ready()

    def matches(self, pattern) -> bool:
        if pattern.startswith("/") and self.id.startswith(pattern[1:]):
            return True
        elif self.display_name == pattern:
            return True
        elif self.file_path.endswith(pattern):
            return True
        return False

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

    def copy(self) -> "TestCase":
        return deepcopy(self)

    def add_dependency(self, *cases: Union["TestCase", str]) -> None:
        for case in cases:
            if isinstance(case, TestCase):
                self.dependencies.append(case)
            else:
                self.dep_patterns.append(case)

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
                    logging.warning(f"{os.path.basename(dst)} already exists in {workdir}")
                    continue
                if action == "copy" or copy_all_resources:
                    fs.force_copy(src, dst, echo=logging.info)
                else:
                    relsrc = os.path.relpath(src, workdir)
                    fs.force_symlink(relsrc, dst, echo=logging.info)

    def save(self):
        file = self.dbfile
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            dump(self, fh)

    def refresh(self) -> None:
        file = self.dbfile
        if not os.path.exists(file):
            raise FileNotFoundError(file)
        with open(file, "r") as fh:
            state = json.load(fh)
        for name, value in state["properties"].items():
            if name in ("start", "finish", "returncode", "exec_root", "status"):
                setattr(self, name, value)
        for dep in self.dependencies:
            dep.refresh()

    @contextmanager
    def rc_environ(self) -> Generator[None, None, None]:
        save_env = os.environ.copy()
        variables = dict(PYTHONPATH=self.pythonpath)
        vars = {}
        vars["cpu_ids"] = variables["NVTEST_CPU_IDS"] = ",".join(map(str, self.cpu_ids))
        vars["gpu_ids"] = variables["NVTEST_GPU_IDS"] = ",".join(map(str, self.gpu_ids))
        for key, value in self.variables.items():
            variables[key] = value % vars
        for var, val in variables.items():
            os.environ[var] = val
        os.environ["PATH"] = f"{self.exec_dir}:{os.environ['PATH']}"
        yield
        os.environ.clear()
        os.environ.update(save_env)

    def output(self, compress: bool = False) -> str:
        if not self.status.complete():
            return "Log not found"
        text = io.open(self.logfile(), errors="ignore").read()
        if compress:
            kb_to_keep = 2 if self.status == "success" else 300
            text = compress_str(text, kb_to_keep=kb_to_keep)
        return text

    def setup(self, exec_root: str, copy_all_resources: bool = False) -> None:
        logging.trace(f"Setting up {self}")
        if self.exec_root is not None:
            assert os.path.samefile(exec_root, self.exec_root)
        self.exec_root = exec_root
        if os.path.exists(self.exec_dir):
            with fs.working_dir(self.exec_dir):
                for f in os.listdir("."):
                    fs.force_remove(f)
        with fs.working_dir(self.exec_dir, create=True):
            self.setup_exec_dir(copy_all_resources=copy_all_resources)
            self._status.set("ready" if not self.dependencies else "pending")
            for hook in plugin.plugins():
                hook.test_setup(self)
            self.save()
        logging.trace(f"Done setting up {self}")

    def setup_exec_dir(self, copy_all_resources: bool = False) -> None:
        with logging.capture(self.logfile("setup"), mode="w"):
            with logging.timestamps():
                logging.info(f"Preparing test: {self.name}")
                logging.info(f"Directory: {os.getcwd()}")
                logging.info("Cleaning work directory...")
                logging.info("Linking and copying working files...")
                if copy_all_resources:
                    fs.force_copy(self.file, os.path.basename(self.file), echo=logging.info)
                else:
                    relsrc = os.path.relpath(self.file, os.getcwd())
                    fs.force_symlink(relsrc, os.path.basename(self.file), echo=logging.info)
                self.copy_sources_to_workdir(copy_all_resources=copy_all_resources)

    def do_baseline(self) -> None:
        if not self.baseline:
            return
        logging.info(f"Rebaselining {self.pretty_repr()}")
        with fs.working_dir(self.exec_dir):
            for hook in plugin.plugins():
                hook.test_prepare(self, stage="baseline")
            for arg in self.baseline:
                if isinstance(arg, str):
                    if os.path.exists(arg):
                        args = []
                        exe = Executable(arg)
                    else:
                        args = [os.path.basename(self.file), arg]
                        exe = Executable(sys.executable)
                    with self.rc_environ():
                        exe(*args, fail_on_error=False)
                else:
                    a, b = arg
                    src = os.path.join(self.exec_dir, a)
                    dst = os.path.join(self.file_dir, b)
                    if os.path.exists(src):
                        logging.emit(f"    Replacing {b} with {a}\n")
                        copyfile(src, dst)

    def do_analyze(self) -> None:
        args = ["--execute-analysis-sections"]
        return self.run(*args, stage="analyze")

    def start_msg(self) -> str:
        id = colorize("@b{%s}" % self.id[:7])
        return "STARTING: {0} {1}".format(id, self.pretty_repr())

    def end_msg(self) -> str:
        id = colorize("@b{%s}" % self.id[:7])
        return "FINISHED: {0} {1} {2}".format(id, self.pretty_repr(), self.status.cname)

    def run(
        self,
        *args: str,
        stage: str = "test",
        timeoutx: float = 1.0,
        **kwargs: Any,
    ) -> None:
        if os.getenv("NVTEST_RESETUP"):
            assert isinstance(self.exec_root, str)
            self.setup(self.exec_root)
        if self.dep_patterns:
            raise RuntimeError("Dependency patterns must be resolved before running")
        try:
            self.start = timestamp()
            self.finish = -1
            self.returncode = self.do_run(*args, stage=stage, timeoutx=timeoutx)
            if self.xstatus == diff_exit_status:
                if self.returncode != diff_exit_status:
                    self._status.set("failed", f"expected {self.name} to diff")
                else:
                    self._status.set("xdiff")
            elif self.xstatus != 0:
                # Expected to fail
                code = self.xstatus
                if code > 0 and self.returncode != code:
                    self._status.set("failed", f"expected {self.name} to exit with code={code}")
                elif self.returncode == 0:
                    self._status.set("failed", f"expected {self.name} to exit with code != 0")
                else:
                    self._status.set("xfail")
            else:
                self._status.set_from_code(self.returncode)
        except KeyboardInterrupt:
            self.returncode = 2
            self._status.set("cancelled", "keyboard interrupt")
            time.sleep(0.01)
            raise
        except BaseException:
            self.returncode = 1
            self._status.set("failed", "unknown failure")
            time.sleep(0.01)
            raise
        finally:
            self.finish = timestamp()
            self.cache_runtime()
            self.save()
            with open(self.logfile(), "w") as fh:
                for stage in ("setup", "test", "analyze"):
                    file = self.logfile(stage)
                    if os.path.exists(file):
                        fh.write(open(file).read())
            for hook in plugin.plugins():
                hook.test_finish(self)
        return

    def do_run(self, *args: str, stage: str = "test", timeoutx: float = 1.0) -> int:
        self._status.set("running")
        self.save()
        timeout = self.timeout * timeoutx
        assert stage in ("test", "analyze")
        with fs.working_dir(self.exec_dir):
            for hook in plugin.plugins():
                hook.test_prepare(self, stage=stage)
            with logging.capture(self.logfile(stage), mode="w"), logging.timestamps():
                cmd: list[str] = []
                if self.launcher:
                    cmd.append(self.launcher)
                    cmd.extend(self.preflags or [])
                cmd.append(self.command)
                cmd.extend(self.postflags or [])
                cmd.extend(args)
                self.cmd_line = " ".join(cmd)
                logging.info(f"Running {self.display_name}")
                logging.info(f"Command line: {self.cmd_line}")
                if timeoutx != 1.0:
                    logging.info(f"Timeout multiplier: {timeoutx}")
                with self.rc_environ():
                    start = time.monotonic()
                    proc = subprocess.Popen(cmd, start_new_session=True)
                    while True:
                        if proc.poll() is not None:
                            break
                        if timeout > 0 and time.monotonic() - start > timeout:
                            os.kill(proc.pid, signal.SIGINT)
                            return -2
                        time.sleep(0.05)
                    return proc.returncode

    def teardown(self) -> None: ...

    def dump(self, fname: Union[str, IO[Any]]) -> None:
        file: IO[Any]
        own_fh = False
        if isinstance(fname, str):
            file = open(fname, "w")
            own_fh = True
        else:
            file = fname
        state = self.getstate()
        json.dump(state, file, indent=2)
        if own_fh:
            file.close()

    def getstate(self) -> dict[str, Any]:
        """Return a serializable dictionary from which the test case can be later loaded"""
        state: dict[str, Any] = {"type": self.__class__.__name__}
        properties = state.setdefault("properties", {})
        for attr, value in self.__dict__.items():
            private = attr.startswith("_")
            name = attr[1:] if private else attr
            if name == "dependencies":
                value = [dep.getstate() for dep in value]
            elif name == "status":
                value = {"value": value.value, "details": value.details}
            elif name == "paramsets":
                value = [{"keys": p.keys, "values": p.values} for p in value]
            elif isinstance(value, (list, dict)):
                value = value
            else:
                if not isinstance(value, (str, float, int, type(None))):
                    raise TypeError(f"Cannot serialize {name} = {value}")
            properties[name] = value
        return state

    def setstate(self, state: dict[str, Any]) -> None:
        """The reverse of getstate - set the object state from a dict"""
        # replace values in state with their instantiated objects
        properties = state["properties"]
        for name, value in properties.items():
            if name == "paramsets":
                properties[name] = [ParameterSet(p["keys"], p["values"]) for p in value]
            elif name == "dependencies":
                for i, dep_state in enumerate(value):
                    value[i] = factory(dep_state.pop("type"))
                    value[i].setstate(dep_state)
                properties[name] = value
            elif name == "status":
                properties[name] = Status(value["value"], details=value["details"])
        for name, value in properties.items():
            if name == "dependencies":
                for dep in value:
                    self.add_dependency(dep)
            elif name == "cpu_ids":
                self._cpu_ids = value
            elif name == "gpu_ids":
                self._gpu_ids = value
            elif value is not None:
                setattr(self, name, value)
        return


class TestMultiCase(TestCase):
    def __init__(
        self,
        file_root: Optional[str] = None,
        file_path: Optional[str] = None,
        *,
        flag: Optional[str] = None,
        paramsets: Optional[list[ParameterSet]] = None,
        family: Optional[str] = None,
        keywords: list[str] = [],
        timeout: Optional[float] = None,
        baseline: list[Union[str, tuple[str, str]]] = [],
        sources: dict[str, list[tuple[str, str]]] = {},
        xstatus: int = 0,
        preload: Optional[str] = None,
    ):
        super().__init__(
            file_root=file_root,
            file_path=file_path,
            family=family,
            keywords=keywords,
            timeout=timeout,
            baseline=baseline,
            sources=sources,
            xstatus=xstatus,
            preload=preload,
        )
        self._flag = flag
        self._paramsets = paramsets

    @property
    def flag(self) -> str:
        assert self._flag is not None
        return self._flag

    @flag.setter
    def flag(self, arg: str) -> None:
        self._flag = arg

    @property
    def postflags(self) -> list[str]:
        if self._postflags is None:
            if self.flag.startswith("-"):
                self._postflags = [self.flag]
        return self._postflags or []

    @postflags.setter
    def postflags(self, arg: list[str]) -> None:
        self._postflags = arg

    @property
    def command(self) -> str:
        if self._command is None:
            if self.flag.startswith("-"):
                self._command = os.path.basename(self.file)
                return self._command
            else:
                self._command = self.flag
        assert self._command is not None
        return self._command

    @command.setter
    def command(self, arg: str) -> None:
        self._command = arg

    @property
    def paramsets(self) -> list[ParameterSet]:
        assert self._paramsets is not None
        return self._paramsets

    @paramsets.setter
    def paramsets(self, arg: list[ParameterSet]) -> None:
        self._paramsets = arg
        if self._paramsets:
            assert isinstance(self._paramsets[0], ParameterSet)

    def do_analyze(self) -> None:
        return self.run(stage="analyze")


def factory(type: str, **kwargs: Any) -> Union[TestCase, TestMultiCase]:
    """The reverse of getstate - return a test case from a dictionary"""

    case: Union[TestCase, TestMultiCase]
    if type == "TestCase":
        case = TestCase()
    else:
        for T in TestCase.REGISTRY:
            if T.__name__ == type:
                case = T()
                break
        else:
            raise ValueError(type)
    return case


def getstate(case: Union[TestCase, TestMultiCase]) -> dict[str, Any]:
    """Return a serializable dictionary from which the test case can be later loaded"""
    return case.getstate()


def dump(case: Union[TestCase, TestMultiCase], fname: Union[str, IO[Any]]) -> None:
    case.dump(fname)


def from_state(state: dict[str, Any]) -> Union[TestCase, TestMultiCase]:
    case = factory(state.pop("type"))
    case.setstate(state)
    return case


class MissingSourceError(Exception):
    pass
