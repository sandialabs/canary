import dataclasses
import datetime
import fnmatch
import io
import itertools
import json
import math
import os
import re
import sys
from contextlib import contextmanager
from copy import deepcopy
from typing import IO
from typing import Any
from typing import Generator
from typing import Type

from .. import config
from .. import plugin
from ..atc import AbstractTestCase
from ..paramset import ParameterSet
from ..status import Status
from ..third_party.color import colorize
from ..util import cache
from ..util import filesystem as fs
from ..util import logging
from ..util.compression import compress_str
from ..util.executable import Executable
from ..util.filesystem import copyfile
from ..util.filesystem import mkdirp
from ..util.hash import hashit
from ..util.module import load_module
from ..util.shell import source_rcfile
from ..when import match_any


def stringify(arg: Any, float_fmt: str | None = None) -> str:
    """Turn the thing into a string"""
    if isinstance(arg, float) and float_fmt is not None:
        return float_fmt % arg
    if hasattr(arg, "string"):
        return arg.string
    elif isinstance(arg, float):
        return f"{arg:g}"
    elif isinstance(arg, int):
        return f"{arg:d}"
    return str(arg)


@dataclasses.dataclass
class Asset:
    src: str
    dst: str | None
    action: str


@dataclasses.dataclass
class DependencyPatterns:
    """String representation of test dependencies

    Dependency resolution is performed after test case discovery.  The ``DependencyPatterns``
    object holds information needed to perform the resolution.

    Args:
      value: The dependency name or glob pattern.
      expect: For glob patterns, how many dependencies are expected to be found
      result: The test case will run if the dependency exits with this status.  Usually ``success``

    """

    value: str | list[str]
    expect: str | int | None
    result: str

    def __post_init__(self):
        if isinstance(self.value, str):
            self.value = self.value.split()

    def evaluate(self, cases: list["TestCase"], extra_fields: bool = False) -> list["TestCase"]:
        matches: set[TestCase] = set()

        def match(name, pattern):
            return name == pattern or fnmatch.fnmatchcase(name, pattern)

        for case in cases:
            names = {case.name}
            if extra_fields:
                names.update((case.fullname, case.display_name))
                names.add(os.path.join(os.path.dirname(case.file_path), case.name))
                names.add(os.path.join(os.path.dirname(case.file_path), case.display_name))
            for pattern in self.value:
                for name in names:
                    if match(name, pattern):
                        matches.add(case)
                        break
        return list(matches)


class TestCase(AbstractTestCase):
    """Manages the configuration, execution, and dependencies of a test case.

    Args:
      file_root: The root directory for the test files.
      file_path: The relative path to the test file.
      family: The family name of the test.
      keywords: A list of keywords associated with the test.
      parameters: Parameters for the test case.
      timeout: Timeout for the test case execution.
      baseline: Baseline data for comparison.
      sources: Source files for the test.
      xstatus: Exit status for the test case.
      preload: Preload configuration for the test case.
      modules: List of modules to be used in the test.
      rcfiles: List of configuration files for the test.
      owners: List of owners responsible for the test.
      artifacts: Artifacts produced by the test.
      exclusive: Whether the test case is exclusive.
      stages: Stages of the test case execution.

    Attributes:
      _lockfile: The name of the lock file associated with the test case.
      REGISTRY: A registry of all test case subclasses.

    """

    _lockfile = "testcase.lock"

    REGISTRY: set[Type["TestCase"]] = set()

    def __init_subclass__(cls, **kwargs):
        cls.REGISTRY.add(cls)
        return super().__init_subclass__(**kwargs)

    def __init__(
        self,
        file_root: str | None = None,
        file_path: str | None = None,
        *,
        family: str | None = None,
        keywords: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        timeout: float | None = None,
        baseline: list[str | tuple[str, str]] | None = None,
        sources: dict[str, list[tuple[str, str | None]]] | None = None,
        xstatus: int | None = None,
        preload: str | None = None,
        modules: list[str] | None = None,
        rcfiles: list[str] | None = None,
        owners: list[str] | None = None,
        artifacts: list[dict[str, str]] | None = None,
        exclusive: bool = False,
        stages: list[str] | None = None,
    ):
        super().__init__()

        # We need to be able to dump the test case to a json file and then reload it.  To do so, we
        # initialize all attributes as private and employ getters/setters
        self._file_root: str = ""
        self._file_path: str = ""
        self._url: str | None = None
        self._family: str = ""
        self._classname: str | None = None
        self._keywords: list[str] = []
        self._parameters: dict[str, Any] = {}
        self._timeout: float | None = None
        self._baseline: list[str | tuple[str, str]] = []
        self._assets: list[Asset] = []
        self._xstatus: int = 0
        self._preload: str | None = None
        self._modules: list[str] = []
        self._rcfiles: list[str] = []
        self._owners: list[str] = []
        self._artifacts: list[dict[str, str]] = []
        self._exclusive: bool = exclusive

        self._mask: str | None = None
        self._name: str | None = None
        self._display_name: str | None = None
        self._id: str | None = None
        self._status: Status = Status()
        self._cmd_line: str | None = None
        self._work_tree: str | None = None
        self._working_directory: str | None = None

        # The process running the test case
        self._start: float = -1.0
        self._finish: float = -1.0
        self._returncode: int = -1

        # Dependency management
        self._unresolved_dependencies: list[DependencyPatterns] = []
        self._dependencies: list["TestCase"] = []
        self._dep_done_criteria: list[str] = []

        # mean, min, max runtimes
        self._runtimes: list[float | None] = [None, None, None]

        self._launcher: str | None = None
        self._preflags: list[str] | None = None
        self._exe: str | None = None
        self._postflags: list[str] | None = None

        # Environment variables specific to this case
        self._variables: dict[str, str] = {}

        self._measurements: dict[str, Any] = {}

        self.stages: list[str] = stages or ["run"]

        if file_root is not None:
            self.file_root = file_root
        if file_path is not None:
            self.file_path = file_path
        if family is not None:
            self.family = family
        if owners is not None:
            self.owners = owners
        if keywords is not None:
            self.keywords = keywords
        if parameters is not None:
            self.parameters = parameters
        if timeout is not None:
            self.timeout = float(timeout)
        if baseline is not None:
            self.baseline = baseline
        if sources is not None:
            self.assets = sources  # type: ignore
        if xstatus is not None:
            self.xstatus = xstatus
        if preload is not None:
            self.preload = preload
        if modules is not None:
            self.modules = modules
        if rcfiles is not None:
            self.rcfiles = rcfiles
        if artifacts is not None:
            self.artifacts = artifacts

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
    def lockfile(self) -> str:
        """Path to lock file containing information needed to generate this case at runtime"""
        file = os.path.join(self.cache_directory, self._lockfile)
        return file

    @property
    def file_root(self) -> str:
        """Source file root, e.g., the stem of the search path used to find this file"""
        assert self._file_root is not None
        return self._file_root

    @file_root.setter
    def file_root(self, arg: str) -> None:
        assert os.path.exists(arg)
        self._file_root = arg

    @property
    def file_path(self) -> str:
        """Source file path, e.g., the relative path from file_root to the file"""
        assert self._file_path is not None
        return self._file_path

    @file_path.setter
    def file_path(self, arg: str) -> None:
        assert os.path.exists(os.path.join(self.file_root, arg))
        self._file_path = arg

    @property
    def file(self) -> str:
        """Full source file path"""
        return os.path.join(self.file_root, self.file_path)

    @property
    def file_dir(self) -> str:
        return os.path.dirname(self.file)

    @property
    def work_tree(self) -> str | None:
        """The session work tree.  Can be lazily evaluated so we don't set it here if missing"""
        return self._work_tree

    @work_tree.setter
    def work_tree(self, arg: str | None) -> None:
        if arg is not None:
            assert os.path.exists(arg)
            self._work_tree = arg

    # Backward compatibility
    exec_root = work_tree

    @property
    def path(self) -> str:
        """The relative path from ``self.work_tree`` to ``self.cache_directory``"""
        if os.getenv("VVTEST_PATH_NAMING_CONVENTION", "yes").lower() in ("yes", "true", "1", "on"):
            return os.path.join(os.path.dirname(self.file_path), self.name)
        return os.path.join(self.id[:2], self.id[2:])

    # backward compatibility
    exec_path = path

    @property
    def cache_directory(self) -> str:
        """Directory where output and lock files are written"""
        work_tree = self.work_tree
        if not work_tree:
            work_tree = config.session.work_tree
        if not work_tree:
            raise ValueError("work_tree must be set during set up") from None
        return os.path.normpath(os.path.join(work_tree, self.path))

    @property
    def working_directory(self) -> str:
        """Directory where the test is executed.  Usually the same as the cache_directory.  For
        CTests, the working_directory is set to the tests binary directory"""
        if self._working_directory is None:
            self._working_directory = self.cache_directory
        return self._working_directory

    @working_directory.setter
    def working_directory(self, arg: str) -> None:
        self._working_directory = arg

    @property
    def family(self) -> str:
        """The test family.  Usually the basename of the file"""
        if not self._family:
            self._family = os.path.splitext(os.path.basename(self.file_path))[0]
        return self._family

    @family.setter
    def family(self, arg: str) -> None:
        self._family = arg

    @property
    def owners(self) -> list[str]:
        """Test owners"""
        return self._owners

    @owners.setter
    def owners(self, arg: list[str]) -> None:
        self._owners = list(arg)

    @property
    def keywords(self) -> list[str]:
        """Test keywords (labels)"""
        return self._keywords

    @keywords.setter
    def keywords(self, arg: list[str]) -> None:
        self._keywords = list(arg)

    @property
    def implicit_keywords(self) -> list[str]:
        """Implicit keywords, used for some filtering operations"""
        kwds = {self.status.name.lower(), self.status.value.lower(), self.name, self.family}
        return list(kwds)

    @property
    def parameters(self) -> dict[str, Any]:
        """This test's parameters"""
        return self._parameters

    @parameters.setter
    def parameters(self, arg: dict[str, Any]) -> None:
        self._parameters = dict(arg)
        np = self._parameters.get("np") or 1
        if not isinstance(np, int):
            class_name = np.__class__.__name__
            raise ValueError(f"{self.family}: expected np={np} to be an int, not {class_name}")
        for key in ("ngpu", "ndevice"):
            if key in self._parameters:
                nd = self._parameters[key]
                if not isinstance(nd, int) and nd is not None:
                    class_name = nd.__class__.__name__
                    raise ValueError(
                        f"{self.family}: expected {key}={nd} " f"to be an int, not {class_name}"
                    )

    @property
    def unresolved_dependencies(self) -> list[DependencyPatterns]:
        """List of dependency patterns that must be resolved before running"""
        return self._unresolved_dependencies

    @unresolved_dependencies.setter
    def unresolved_dependencies(self, arg: list[DependencyPatterns]) -> None:
        self._unresolved_dependencies = list(arg)

    @property
    def dep_done_criteria(self) -> list[str]:
        """``dep_done_criteria[i]`` is the expected exit status of the ``i``\ th dependency.  This
        case will not run unless the ``i``\ th dependency exits with this status.  Usually
        ``dep_done_criteria[i]`` is 'success'.
        """
        return self._dep_done_criteria

    @dep_done_criteria.setter
    def dep_done_criteria(self, arg: list[str]) -> None:
        self._dep_done_criteria = list(arg)

    @property
    def dependencies(self) -> list["TestCase"]:
        """This test's dependencies"""
        return self._dependencies

    @dependencies.setter
    def dependencies(self, arg: list["TestCase"]) -> None:
        self._dependencies = arg

    @property
    def runtimes(self) -> list[float | None]:
        """Basic running time information.  If run continually in the same session, this data can
        be used in optimizing test submission.

        Returns:
          runtimes: Running time metrics
            ``runtimes[0]``: minimum time recorded
            ``runtimes[1]``: mean time recorded
            ``runtimes[2]``: maximum time recorded

        """
        if self._runtimes[0] is None:
            self.load_runtimes()
        return self._runtimes

    @runtimes.setter
    def runtimes(self, arg: list[float | None]) -> None:
        self._runtimes = arg

    @property
    def timeout(self) -> float:
        """This test's timeout.  See :meth:`set_default_timeout`"""
        if self._timeout is None:
            self.set_default_timeout()
        if not isinstance(self._timeout, (int, float)):
            logging.warning(f"{self}: expected timeout to be a number but got {self.timeout=}")
            self._timeout = float(self._timeout)  # type: ignore
        return self._timeout

    @timeout.setter
    def timeout(self, arg: float) -> None:
        self._timeout = float(arg)

    @property
    def baseline(self) -> list[str | tuple[str, str]]:
        return self._baseline

    @baseline.setter
    def baseline(self, arg: list[str | tuple[str, str]]) -> None:
        self._baseline = list(arg)

    @property
    def assets(self) -> list[Asset]:
        return self._assets

    @assets.setter
    def assets(self, arg: dict[str, list[tuple[str, str | None]]]) -> None:
        """Transfer source files to this test case's assets.

        {action: [(src, dst), ...]}

        """
        self._assets.clear()
        for action in arg:
            for t, dst in arg[action]:
                src = t if os.path.isabs(t) else os.path.join(self.file_dir, t)
                if not os.path.exists(src):
                    logging.warning(f"{self}: {action} resource file {t} not found")
                asset = Asset(src=os.path.abspath(src), dst=dst, action=action)
                self._assets.append(asset)

    @property
    def xstatus(self) -> int:
        return self._xstatus

    @xstatus.setter
    def xstatus(self, arg: int) -> None:
        self._xstatus = arg

    @property
    def preload(self) -> str | None:
        return self._preload

    @preload.setter
    def preload(self, arg: str | None) -> None:
        self._preload = arg

    @property
    def modules(self) -> list[str]:
        return self._modules

    @modules.setter
    def modules(self, arg: list[str]) -> None:
        self._modules = arg

    @property
    def rcfiles(self) -> list[str]:
        return self._rcfiles

    @rcfiles.setter
    def rcfiles(self, arg: list[str]) -> None:
        self._rcfiles = arg

    @property
    def artifacts(self) -> list[dict[str, str]]:
        return self._artifacts

    @artifacts.setter
    def artifacts(self, arg: list[dict[str, str]]) -> None:
        self._artifacts = arg

    @property
    def exclusive(self) -> bool:
        return self._exclusive

    @exclusive.setter
    def exclusive(self, arg: bool) -> None:
        self._exclusive = arg

    @property
    def skipped(self) -> bool:
        return self.status == "skipped"

    @property
    def status(self) -> Status:
        if self._status.pending():
            if not self.dependencies:
                raise ValueError("should never have a pending case without dependencies")
            # Determine if dependent cases have completed and, if so, flip status to 'ready'
            expected = self.dep_done_criteria
            ready: list[bool] = [False] * len(self.dependencies)
            for i, dep in enumerate(self.dependencies):
                if dep.status.value not in ("ready", "pending", "running"):
                    if expected[i] in (None, dep.status.value, "*"):
                        ready[i] = True
                    else:
                        ready[i] = match_any(expected[i], [dep.status.value, dep.status.name])
                    if ready[i] is False:
                        # this case will never be able to run
                        if dep.status == "skipped":
                            self._status.set("skipped", "one or more dependencies was skipped")
                        elif dep.status == "cancelled":
                            self._status.set("not_run", "one or more dependencies was cancelled")
                        elif dep.status == "timeout":
                            self._status.set("not_run", "one or more dependencies timed out")
                        elif dep.status == "failed":
                            self._status.set("not_run", "one or more dependencies failed")
                        elif dep.status == "diffed":
                            self._status.set("skipped", "one or more dependencies diffed")
                        else:
                            self._status.set(
                                "skipped",
                                f"one or more dependencies failed with status {dep.status.value}",
                            )
            if all(ready):
                self._status.set("ready")
        return self._status

    @status.setter
    def status(self, arg: Status | dict[str, str]) -> None:
        if isinstance(arg, Status):
            self._status.set(arg.value, details=arg.details)
        elif isinstance(arg, dict):
            self._status.set(arg["value"], details=arg["details"])
        else:
            raise ValueError(arg)

    @property
    def url(self) -> str | None:
        return self._url

    @url.setter
    def url(self, arg: str) -> None:
        self._url = arg

    @property
    def launcher(self) -> str | None:
        return self._launcher

    @launcher.setter
    def launcher(self, arg: str | None) -> None:
        self._launcher = arg

    @property
    def preflags(self) -> list[str]:
        return self._preflags or []

    @preflags.setter
    def preflags(self, arg: list[str]) -> None:
        self._preflags = arg

    @property
    def postflags(self) -> list[str]:
        if self._postflags is None:
            self._postflags = []
        return self._postflags

    @postflags.setter
    def postflags(self, arg: list[str]) -> None:
        self._postflags = arg

    @property
    def exe(self) -> str:
        if self._exe is None:
            self._exe = os.path.basename(self.file)
        assert self._exe is not None
        return self._exe

    @exe.setter
    def exe(self, arg: str) -> None:
        self._exe = arg

    def command(self, stage: str = "run") -> list[str]:
        cmd: list[str] = []
        if self.launcher:
            cmd.append(self.launcher)
            cmd.extend(self.preflags or [])
        cmd.append(self.exe)
        if self.file.endswith(".pyt"):
            cmd.append(f"--stage={stage}")
        if self.file.endswith(".vvt") and stage == "analyze":
            cmd.append("--execute-analysis-sections")
        cmd.extend(self.postflags or [])
        return cmd

    @property
    def variables(self) -> dict[str, str]:
        return self._variables

    @variables.setter
    def variables(self, arg: dict[str, str]) -> None:
        self._variables = dict(arg)

    @property
    def measurements(self) -> dict[str, Any]:
        return self._measurements

    @measurements.setter
    def measurements(self, arg: dict[str, Any]) -> None:
        self._measurements = dict(arg)

    @property
    def masked(self) -> bool:
        return True if self._mask else False

    @property
    def mask(self) -> str | None:
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
        """The name displayed to the console"""
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
            classname = os.path.dirname(self.file_path).strip()
            if not classname:
                classname = os.path.basename(self.file_dir).strip()
            self._classname = classname.replace(os.path.sep, ".")
        return self._classname

    @classname.setter
    def classname(self, arg: str) -> None:
        self._classname = arg

    @property
    def cmd_line(self) -> str | None:
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
        self._finish = -1

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
        stage = config.session.stage or "run"
        if stage != "run":
            return 1
        return int(self.parameters.get("np") or 1)  # type: ignore

    @property
    def processors(self) -> int:
        return self.cpus

    @property
    def nodes(self) -> int:
        if "nnode" in self.parameters:
            return int(self.parameters["nnode"])  # type: ignore
        else:
            cpus_per_node = config.machine.cpus_per_node
            nodes = math.ceil(self.cpus / cpus_per_node)
            return nodes

    @property
    def gpus(self) -> int:
        if "ngpu" in self.parameters:
            return int(self.parameters["ngpu"])  # type: ignore
        elif "ndevice" in self.parameters:
            return int(self.parameters["ndevice"])  # type: ignore
        else:
            return 0

    @property
    def cputime(self) -> float | int:
        return self.runtime * self.cpus

    @property
    def runtime(self) -> float | int:
        if self._runtimes[0] is None:
            return self.timeout
        return self._runtimes[0]

    @property
    def pythonpath(self):
        path = [_ for _ in os.getenv("PYTHONPATH", "").split(os.pathsep) if _.split()]
        if self.working_directory not in path:
            path.insert(0, self.working_directory)
        else:
            path.insert(0, path.pop(path.index(self.working_directory)))
        return os.pathsep.join(path)

    def logfile(self, stage: str | None = None) -> str:
        if stage is None:
            return os.path.join(self.cache_directory, "nvtest-out.txt")
        return os.path.join(self.cache_directory, f"nvtest-{stage}-out.txt")

    def set_default_names(self) -> None:
        self.name = self.family
        self.display_name = self.family
        if self.parameters:
            keys = sorted(self.parameters.keys())
            s_vals = [stringify(self.parameters[k]) for k in keys]
            s_params = [f"{k}={s_vals[i]}" for (i, k) in enumerate(keys)]
            self.name = f"{self._name}.{'.'.join(s_params)}"
            self.display_name = f"{self._display_name}[{','.join(s_params)}]"

    def set_default_timeout(self) -> None:
        """Sets the default timeout.  If runtime statistics have been collected those will be used,
        otherwise the timeout will be based on the presence of the long or fast keywords
        """
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
            timeout = config.test.timeout_fast
        elif "long" in self.keywords:
            timeout = config.test.timeout_long
        else:
            timeout = config.test.timeout_default
        self._timeout = float(timeout)

    def load_runtimes(self):
        # return mean, min, max runtimes
        if not config.cache_runtimes:
            return [None, None, None]
        global_cache = cache.get_cache_dir(self.file_root)
        file = self.cache_file(global_cache)
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
        if not config.cache_runtimes:
            return
        if self.status.value not in ("success", "diffed"):
            return
        global_cache = cache.create_cache_dir(self.file_root)
        if global_cache is None:
            return
        file = self.cache_file(global_cache)
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

    def add_measurement(self, **kwds: Any) -> None:
        self.measurements.update(kwds)

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
        if self.status == "skipped":
            string += ": Skipped because %s" % self.status.details
        elif self.duration >= 0:
            today = datetime.datetime.today()
            start = datetime.datetime.fromtimestamp(self.start)
            finish = datetime.datetime.fromtimestamp(self.finish)
            dt = today - start
            fmt = "%H:%m:%S" if dt.days <= 1 else "%M %d %H:%m:%S"
            a = start.strftime(fmt)
            b = finish.strftime(fmt)
            string += f" started: {a}, finished: {b}, duration: {self.duration:.2f}s."
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
        elif self.name == pattern:
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

    def add_dependency(self, case: "TestCase", /, expected_result: str = "success"):
        self.dependencies.append(case)
        self.dep_done_criteria.append(expected_result)
        assert len(self.dependencies) == len(self.dep_done_criteria)

    def copy_sources_to_workdir(self, copy_all_resources: bool = False):
        workdir = self.working_directory
        for asset in self.assets:
            if asset.action not in ("copy", "link"):
                continue
            if not os.path.exists(asset.src):
                s = f"{self.file}: {asset.action} resource file {asset.src} not found"
                raise MissingSourceError(s)
            dst: str
            if asset.dst is None:
                dst = os.path.join(self.working_directory, os.path.basename(asset.src))
            else:
                dst = os.path.join(self.working_directory, asset.dst)
            if asset.action == "copy" or copy_all_resources:
                fs.force_copy(asset.src, dst, echo=logging.info)
            else:
                relsrc = os.path.relpath(asset.src, workdir)
                fs.force_symlink(relsrc, dst, echo=logging.info)

    def save(self):
        file = self.lockfile
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            self.dump(fh)

    def refresh(self, propagate: bool = True) -> None:
        file = self.lockfile
        if not os.path.exists(file):
            raise FileNotFoundError(file)
        with open(file, "r") as fh:
            state = json.load(fh)
        keep = (
            "start",
            "finish",
            "returncode",
            "work_tree",
            "status",
            "measurements",
            "dep_done_criteria",
        )
        for name, value in state["properties"].items():
            if name in keep:
                setattr(self, name, value)
        if propagate:
            for dep in self.dependencies:
                dep.refresh()

    @contextmanager
    def rc_environ(self, **variables) -> Generator[None, None, None]:
        save_env = os.environ.copy()
        variables.update(dict(PYTHONPATH=self.pythonpath))
        vars = {}
        vars["cpu_ids"] = variables["NVTEST_CPU_IDS"] = ",".join(map(str, self.cpu_ids))
        vars["gpu_ids"] = variables["NVTEST_GPU_IDS"] = ",".join(map(str, self.gpu_ids))
        for key, value in self.variables.items():
            variables[key] = value % vars
        for var, value in variables.items():
            os.environ[var] = value
        os.environ["PATH"] = f"{self.working_directory}:{os.environ['PATH']}"
        try:
            for module in self.modules:
                load_module(module)
            for rcfile in self.rcfiles:
                source_rcfile(rcfile)
            yield
        finally:
            os.environ.clear()
            os.environ.update(save_env)

    def output(self, compress: bool = False) -> str:
        if not self.status.complete():
            return "Log not found"
        elif self.status == "skipped":
            return "Test skipped"
        text = io.open(self.logfile(), errors="ignore").read()
        if compress:
            kb_to_keep = 2 if self.status == "success" else 300
            text = compress_str(text, kb_to_keep=kb_to_keep)
        return text

    def setup(self, work_tree: str, copy_all_resources: bool = False, clean: bool = True) -> None:
        if len(self.dependencies) != len(self.dep_done_criteria):
            raise ValueError("Inconsistent dependency/dep_done_criteria lists")
        logging.trace(f"Setting up {self}")
        if self.work_tree is not None:
            assert os.path.samefile(work_tree, self.work_tree)
        self.work_tree = work_tree
        clean_out_folder(self.cache_directory)
        fs.mkdirp(self.cache_directory)
        if clean:
            clean_out_folder(self.working_directory)
        with fs.working_dir(self.working_directory, create=True):
            self.setup_working_directory(copy_all_resources=copy_all_resources)
            self._status.set("ready" if not self.dependencies else "pending")
            for hook in plugin.hooks():
                hook.test_setup(self)
            self.save()
        logging.trace(f"Done setting up {self}")

    def setup_working_directory(self, copy_all_resources: bool = False) -> None:
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
        with fs.working_dir(self.working_directory):
            for hook in plugin.hooks():
                hook.test_before_run(self, stage="baseline")
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
                    src = os.path.join(self.working_directory, a)
                    dst = os.path.join(self.file_dir, b)
                    if os.path.exists(src):
                        logging.emit(f"    Replacing {b} with {a}\n")
                        copyfile(src, dst)

    def start_msg(self) -> str:
        id = colorize("@b{%s}" % self.id[:7])
        return "STARTING: {0} {1}".format(id, self.pretty_repr())

    def end_msg(self) -> str:
        id = colorize("@b{%s}" % self.id[:7])
        return "FINISHED: {0} {1} {2}".format(id, self.pretty_repr(), self.status.cname)

    def prepare_for_launch(self, stage: str = "run") -> None:
        if os.getenv("NVTEST_RESETUP"):
            assert isinstance(self.work_tree, str)
            self.setup(self.work_tree)
        if self.unresolved_dependencies:
            raise RuntimeError("All dependencies must be resolved before running")
        with fs.working_dir(self.working_directory):
            for hook in plugin.hooks():
                hook.test_before_run(self, stage=stage)
        self.save()

    def wrap_up(self, stage: str = "run") -> None:
        with fs.working_dir(self.working_directory):
            self.cache_runtime()
            self.save()
            with open(self.logfile(), "w") as fh:
                for stage in ("setup", "run", "analyze"):
                    file = self.logfile(stage)
                    if os.path.exists(file):
                        fh.write(open(file).read())

    def teardown(self) -> None: ...

    def dump(self, fname: str | IO[Any]) -> None:
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
            if attr.startswith("__"):
                # skip *really* private variables
                continue
            private = attr.startswith("_")
            name = attr[1:] if private else attr
            if name == "dependencies":
                value = [dep.getstate() for dep in value]
            elif name == "assets":
                sources: dict[str, list[list[str | None]]] = {}
                for asset in value:
                    sources.setdefault(asset.action, []).append([asset.src, asset.dst])
                value = sources
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
                self.dependencies.clear()
                self.dep_done_criteria.clear()
                for i, dep in enumerate(value):
                    self.add_dependency(dep, properties["dep_done_criteria"][i])
            elif name == "dep_done_criteria":
                continue
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
        file_root: str | None = None,
        file_path: str | None = None,
        *,
        flag: str = "--analyze",
        paramsets: list[ParameterSet] | None = None,
        family: str | None = None,
        keywords: list[str] = [],
        timeout: float | None = None,
        baseline: list[str | tuple[str, str]] = [],
        sources: dict[str, list[tuple[str, str | None]]] = {},
        xstatus: int = 0,
        preload: str | None = None,
        modules: list[str] | None = None,
        rcfiles: list[str] | None = None,
        owners: list[str] | None = None,
        artifacts: list[dict[str, str]] | None = None,
        exclusive: bool = False,
        stages: list[str] | None = None,
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
            modules=modules,
            rcfiles=rcfiles,
            owners=owners,
            artifacts=artifacts,
            exclusive=exclusive,
            stages=stages,
        )
        if "analyze" not in self.stages:
            self.stages.extend("analyze")
        if flag.startswith("-"):
            # for the base case, call back on the test file with ``flag`` on the command line
            self.launcher = sys.executable
            self.exe = os.path.basename(self.file)
            self.postflags.append(flag)
        else:
            src = flag if os.path.exists(flag) else os.path.join(self.file_dir, flag)
            if not os.path.exists(src):
                logging.warning(f"{self}: analyze script {flag} not found")
            self.exe = os.path.basename(flag)
            self.launcher = None
            # flag is a script to run during analysis, check if it is going to be copied/linked
            for asset in self.assets:
                if asset.action in ("link", "copy") and self.exe == os.path.basename(asset.src):
                    break
            else:
                asset = Asset(src=os.path.abspath(src), dst=None, action="link")
                self.assets.append(asset)
        self._flag = flag
        self._paramsets = paramsets

    @property
    def flag(self) -> str:
        assert self._flag is not None
        return self._flag

    @flag.setter
    def flag(self, arg: str) -> None:
        self._flag = arg

    def command(self, stage: str = "run") -> list[str]:
        cmd: list[str] = []
        if self.launcher:
            cmd.append(self.launcher)
            cmd.extend(self.preflags or [])
        cmd.append(self.exe)
        if self.file.endswith(".pyt"):
            cmd.append(f"--stage={stage}")
        cmd.extend(self.postflags or [])
        return cmd

    @property
    def paramsets(self) -> list[ParameterSet]:
        assert self._paramsets is not None
        return self._paramsets

    @paramsets.setter
    def paramsets(self, arg: list[ParameterSet]) -> None:
        self._paramsets = arg
        if self._paramsets:
            assert isinstance(self._paramsets[0], ParameterSet)

    @property
    def cpus(self) -> int:
        return 1


def factory(type: str, **kwargs: Any) -> TestCase | TestMultiCase:
    """The reverse of getstate - return a test case from a dictionary"""

    case: TestCase | TestMultiCase
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


def getstate(case: TestCase | TestMultiCase) -> dict[str, Any]:
    """Return a serializable dictionary from which the test case can be later loaded"""
    return case.getstate()


def dump(case: TestCase | TestMultiCase, fname: str | IO[Any]) -> None:
    case.dump(fname)


def from_state(state: dict[str, Any]) -> TestCase | TestMultiCase:
    case = factory(state.pop("type"))
    case.setstate(state)
    return case


def clean_out_folder(folder: str) -> None:
    if os.path.exists(folder):
        with fs.working_dir(folder):
            for f in os.listdir("."):
                fs.force_remove(f)


class MissingSourceError(Exception):
    pass
