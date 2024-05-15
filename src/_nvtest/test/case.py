import itertools
import json
import os
import pickle
import re
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from copy import deepcopy
from string import Template
from typing import Any
from typing import BinaryIO
from typing import Generator
from typing import Optional
from typing import Union

from .. import config
from .. import plugin
from ..error import diff_exit_status
from ..paramset import ParameterSet
from ..third_party.color import colorize
from ..util import cache
from ..util import filesystem as fs
from ..util import logging
from ..util.compression import compress_file
from ..util.executable import Executable
from ..util.filesystem import copyfile
from ..util.filesystem import mkdirp
from ..util.hash import hashit
from .runner import Runner
from .status import Status


def stringify(arg: Any) -> str:
    if hasattr(arg, "string"):
        return arg.string
    elif isinstance(arg, float):
        return f"{arg:g}"
    elif isinstance(arg, int):
        return f"{arg:d}"
    return str(arg)


class TestCase(Runner):
    def __init__(
        self,
        root: str,
        path: str,
        *,
        family: Optional[str] = None,
        keywords: list[str] = [],
        parameters: dict[str, object] = {},
        timeout: Optional[float] = None,
        baseline: list[Union[str, tuple[str, str]]] = [],
        sources: dict[str, list[tuple[str, str]]] = {},
        xstatus: int = 0,
    ):
        # file properties
        self.file_root = root
        self.file_path = path
        self.file = os.path.join(root, path)
        self.file_dir = os.path.dirname(self.file)
        assert os.path.exists(self.file)
        self.file_type = os.path.splitext(self.file)[1:]
        self._active: Optional[bool] = None

        # Other properties
        self._mask = ""
        self._keywords = keywords
        self.parameters = {} if parameters is None else dict(parameters)
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
        self._status = Status("created")

        self.cmd_line: str = ""
        self.exec_root: Optional[str] = None
        self.exec_path = os.path.join(os.path.dirname(self.file_path), self.name)
        # The process running the test case
        self.start: float = -1
        self.finish: float = -1
        self.returncode: int = -1

        # Dependency management
        self.dep_patterns: list[str] = []
        self.dependencies: list["TestCase"] = []

        self._timeout = timeout
        self._runtimes = self.load_runtimes()
        self.xstatus = xstatus

        self.command = sys.executable

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

    @classmethod
    def load(cls, fh: BinaryIO) -> "TestCase":
        self = pickle.load(fh)
        return self

    @property
    def dbfile(self) -> str:
        tag = sys.implementation.cache_tag
        file = os.path.join(self.exec_dir, ".nvtest", f"case.data.{tag}.p")
        mkdirp(os.path.dirname(file))
        return file

    @property
    def mask(self) -> str:
        return self._mask

    @mask.setter
    def mask(self, arg: str) -> None:
        self._mask = arg

    @property
    def skipped(self) -> bool:
        return self.status == "skipped"

    @property
    def status(self) -> Status:
        if self._status.value == "pending":
            # Determine if dependent cases have completed and, if so, flip status to 'ready'
            if not self.dependencies:
                raise ValueError("should never have a pending case without dependencies")
            stat = [dep.status.value for dep in self.dependencies]
            if all([_ in ("success", "diffed") for _ in stat]):
                self._status.set("ready")
            elif any([_ == "skipped" for _ in stat]):
                self._status.set("skipped", "one or more dependency was skipped")
            elif any([_ == "cancelled" for _ in stat]):
                self._status.set("skipped", "one or more dependency was cancelled")
            elif any([_ == "timeout" for _ in stat]):
                self._status.set("skipped", "one or more dependency timed out")
            elif any([_ == "failed" for _ in stat]):
                self._status.set("skipped", "one or more dependency failed")
        return self._status

    @status.setter
    def status(self, arg: Union[Status, list[str]]) -> None:
        if isinstance(arg, Status):
            self._status.set(arg.value, details=arg.details)
        else:
            self._status.set(arg[0], details=arg[1])

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
            exec_root = config.get("session:root")
        if not exec_root:
            raise ValueError("exec_root must be set during set up") from None
        return os.path.normpath(os.path.join(exec_root, self.exec_path))

    @property
    def processors(self) -> int:
        return int(self.parameters.get("np") or 1)  # type: ignore

    @property
    def devices(self) -> int:
        return int(self.parameters.get("ndevice") or 0)  # type: ignore

    @property
    def cputime(self) -> Union[float, int]:
        return self.runtime * self.processors

    @property
    def runtime(self) -> Union[float, int]:
        if self._runtimes[0] is None:
            return self.timeout
        return self._runtimes[0]

    @property
    def timeout(self) -> float:
        timeout: float
        if self._timeout is not None:
            timeout = float(self._timeout)
        elif self._runtimes[2] is not None:
            max_runtime = self._runtimes[2]
            if max_runtime < 5.0:
                timeout = 20.0
            elif max_runtime < 300.0:
                timeout = 900.0
            else:
                timeout = 2.0 * self._runtimes[2]
        elif "fast" in self._keywords:
            timeout = config.get("test:timeout:fast")
        elif "long" in self._keywords:
            timeout = config.get("test:timeout:long")
        else:
            timeout = config.get("test:timeout:default")
        return timeout

    def add_dependency(self, *cases: Union["TestCase", str]) -> None:
        for case in cases:
            if isinstance(case, TestCase):
                self.dependencies.append(case)
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
                    logging.warning(f"{os.path.basename(dst)} already exists in {workdir}")
                    continue
                if action == "copy" or copy_all_resources:
                    fs.force_copy(src, dst, echo=logging.info)
                else:
                    relsrc = os.path.relpath(src, workdir)
                    fs.force_symlink(relsrc, dst, echo=logging.info)

    def save(self):
        with open(self.dbfile, "wb") as fh:
            self.dump(fh)

    def dump(self, fh) -> None:
        pickle.dump(self, fh)

    def refresh(self) -> None:
        file = self.dbfile
        if not os.path.exists(file):
            raise FileNotFoundError(file)
        with open(file, "rb") as fh:
            case = pickle.load(fh)
        self.start = case.start
        self.finish = case.finish
        self.returncode = case.returncode
        self._status.set(case.status.value, details=case.status.details)
        self.exec_root = case.exec_root
        for dep in self.dependencies:
            dep.refresh()

    @contextmanager
    def rc_environ(self) -> Generator[None, None, None]:
        save_env: dict[str, Optional[str]] = {}
        variables = dict(PYTHONPATH=self.pythonpath)
        variables.update(self.variables)
        for var, val in variables.items():
            save_env[var] = os.environ.pop(var, None)
            os.environ[var] = val
        yield
        for var, save_val in save_env.items():
            if save_val is not None:
                os.environ[var] = save_val
            else:
                os.environ.pop(var)

    def compressed_log(self) -> str:
        done = self.status.value in ("failed", "success")
        if done:
            kb_to_keep = 2 if self.status == "success" else 300
            compressed_log = compress_file(self.logfile(), kb_to_keep)
            return compressed_log
        return "Log not found"

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

    def update(self, attrs: dict[str, object]) -> None:
        for key, val in attrs.items():
            if key == "_status":
                if isinstance(val, (tuple, list)):
                    assert len(val) == 2
                    val = Status(val[0], val[1])
                assert isinstance(val, Status)
            setattr(self, key, val)

    def do_baseline(self) -> None:
        if not self.baseline:
            return
        logging.info(f"Rebaselining {self.pretty_repr()}")
        with fs.working_dir(self.exec_dir):
            for hook in plugin.plugins("test", "setup"):
                hook(self, baseline=True)
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
        return self.run(*args, stage="analyze", analyze=True)

    def start_msg(self) -> str:
        id = colorize("@b{%s}" % self.id[:7])
        return "STARTING: {0} {1}".format(id, self.pretty_repr())

    def end_msg(self) -> str:
        id = colorize("@b{%s}" % self.id[:7])
        return "FINISHED: {0} {1} {2}".format(id, self.pretty_repr(), self.status.cname)

    def run(
        self,
        *args: str,
        stage: Optional[str] = None,
        analyze: bool = False,
        timeoutx: float = 1.0,
        **kwargs: Any,
    ) -> None:
        if os.getenv("NVTEST_RESETUP"):
            assert isinstance(self.exec_root, str)
            self.setup(self.exec_root)
        if self.dep_patterns:
            raise RuntimeError("Dependency patterns must be resolved before running")
        try:
            self.start = time.monotonic()
            self.finish = -1
            self.returncode = self._run(*args, stage=stage, timeoutx=timeoutx, analyze=analyze)
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
            self.finish = time.monotonic()
            self.cache_runtime()
            self.save()
            with open(self.logfile(), "w") as fh:
                for stage in ("setup", "test", "analyze"):
                    file = self.logfile(stage)
                    if os.path.exists(file):
                        fh.write(open(file).read())
            for hook in plugin.plugins("test", "finish"):
                hook(self)
        return

    def _run(
        self,
        *args: str,
        stage: Optional[str] = None,
        analyze: bool = False,
        timeoutx: float = 1.0,
    ) -> int:
        self._status.set("running")
        self.save()
        stage = stage or "test"
        timeout = self.timeout * timeoutx
        with fs.working_dir(self.exec_dir):
            for hook in plugin.plugins("test", "setup"):
                hook(self, analyze=analyze)
            with logging.capture(self.logfile(stage), mode="w"), logging.timestamps():
                cmd = [self.command]
                cmd.extend(self.command_line_args(*args))
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
                        if time.monotonic() - start > timeout:
                            os.kill(proc.pid, signal.SIGINT)
                            return -2
                        time.sleep(0.05)
                    return proc.returncode

    def command_line_args(self, *args: str) -> list[str]:
        command_line_args = [os.path.basename(self.file)]
        command_line_args.extend(args)
        return command_line_args

    def teardown(self) -> None: ...

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


class AnalyzeTestCase(TestCase):
    def __init__(
        self,
        root: str,
        path: str,
        *,
        flag: str,
        paramsets: list[ParameterSet],
        family: Optional[str] = None,
        keywords: list[str] = [],
        timeout: Optional[float] = None,
        baseline: list[Union[str, tuple[str, str]]] = [],
        sources: dict[str, list[tuple[str, str]]] = {},
        xstatus: int = 0,
    ):
        super().__init__(
            root,
            path,
            family=family,
            keywords=keywords,
            timeout=timeout,
            baseline=baseline,
            sources=sources,
            xstatus=xstatus,
        )
        self.flag = flag
        self.paramsets = paramsets

    def do_analyze(self) -> None:
        return self.run(stage="analyze", analyze=True)

    def command_line_args(self, *args: str) -> list[str]:
        if self.flag.startswith("-"):
            command_line_args = [os.path.basename(self.file), self.flag]
        else:
            command_line_args = [self.flag]
        command_line_args.extend(args)
        return command_line_args


class MissingSourceError(Exception):
    pass
