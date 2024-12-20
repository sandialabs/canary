import dataclasses
import datetime
import fnmatch
import hashlib
import io
import itertools
import json
import math
import os
import re
import sys
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from typing import IO
from typing import Any
from typing import Generator
from typing import Type

from .. import config
from .. import plugin
from ..paramset import ParameterSet
from ..status import Status
from ..third_party.color import colorize
from ..util import filesystem as fs
from ..util import logging
from ..util.compression import compress_str
from ..util.executable import Executable
from ..util.filesystem import copyfile
from ..util.filesystem import max_name_length
from ..util.filesystem import mkdirp
from ..util.misc import boolean
from ..util.module import load_module
from ..util.shell import source_rcfile
from ..util.time import hhmmss
from ..when import match_any
from .atc import AbstractTestCase

stats_version_info = (2, 0)


def stringify(arg: Any, float_fmt: str | None = None) -> str:
    """Turn the thing into a string"""
    if hasattr(arg, "string"):
        return arg.string
    if isinstance(arg, float) and float_fmt is not None:
        return float_fmt % arg
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
        self._path: str | None = None

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
        self._environment_modifications: list[dict[str, str]] = []

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
        work_tree = config.session.work_tree
        assert work_tree is not None
        return os.path.join(work_tree, ".nvtest/cases", self.id[:2], self.id[2:], self._lockfile)

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
        """The relative path from ``self.work_tree`` to ``self.working_directory``"""
        if self._path is None:
            work_tree = config.session.work_tree or config.invocation_dir
            dirname, basename = os.path.split(self.file_path)
            path = os.path.join(work_tree, dirname, self.name)
            n = max_name_length()
            if len(os.path.join(path, basename)) < n:
                self._path = os.path.join(dirname, self.name)
            else:
                self._path = os.path.join(dirname, f"{self.family}.{self.id[:7]}")
        assert isinstance(self._path, str)
        return self._path

    @path.setter
    def path(self, arg: str) -> None:
        self._path = arg

    # backward compatibility
    exec_path = path

    def logfile(self, stage: str | None = None) -> str:
        if stage is None:
            return os.path.join(self.working_directory, "nvtest-out.txt")
        return os.path.join(self.working_directory, f"nvtest-{stage}-out.txt")

    @property
    def working_directory(self) -> str:
        """Directory where the test is executed."""
        if self._working_directory is None:
            work_tree = self.work_tree
            if not work_tree:
                work_tree = config.session.work_tree
            if not work_tree:
                raise ValueError("work_tree must be set during set up") from None
            self._working_directory = os.path.normpath(os.path.join(work_tree, self.path))
        assert self._working_directory is not None
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
    def implicit_parameters(self) -> dict[str, int | float]:
        # backward compatibility with vvtest
        parameters: dict[str, int | float] = {}
        if "np" in self.parameters:
            parameters["cpus"] = self.parameters["np"]
        elif "cpus" in self.parameters:
            parameters["np"] = self.parameters["cpus"]
        else:
            parameters["np"] = parameters["cpus"] = 1
        if "ndevice" in self.parameters:
            parameters["gpus"] = self.parameters["ndevice"]
        elif "gpus" in self.parameters:
            parameters["ndevice"] = self.parameters["gpus"]
        else:
            parameters["ndevice"] = parameters["gpus"] = 0
        if "nodes" in self.parameters:
            nodes = self.parameters["nodes"]
            pinfo = config.resource_pool.pinfo
            parameters["cpus"] = parameters["np"] = nodes * pinfo("cpus_per_node")
            parameters["gpus"] = parameters["ndevice"] = nodes * pinfo("gpus_per_node")
        parameters["runtime"] = self.runtime
        return parameters

    def size(self) -> float:
        vec: list[float | int] = [self.timeout]
        for name, value in self.parameters.items():
            if name in config.resource_pool.types:
                assert isinstance(value, int)
                vec.append(value)
        return math.sqrt(sum(_**2 for _ in vec))

    def required_resources(self) -> list[list[dict[str, Any]]]:
        group: list[dict[str, Any]] = []
        parameters = self.parameters | self.implicit_parameters
        for name, value in parameters.items():
            if name.lower() in config.resource_pool.types:
                assert isinstance(value, int)
                group.extend([{"type": name, "slots": 1} for _ in range(value)])
        # by default, only one resource group is returned
        return [group]

    @property
    def parameters(self) -> dict[str, Any]:
        """This test's parameters"""
        return self._parameters

    @parameters.setter
    def parameters(self, arg: dict[str, Any]) -> None:
        if "cpus" in arg and "np" in arg and arg["cpus"] != arg["np"]:
            raise ValueError("parameters cpus and np are mutually exclusive")
        for key in ("cpus", "np"):  # np is for vvtest backward compatibility
            if key in arg:
                if not isinstance(arg[key], int):
                    class_name = arg[key].__class__.__name__
                    raise ValueError(
                        f"{self.family}: expected {key}={arg[key]} to be an int, not {class_name}"
                    )
        if "gpus" in arg and "ndevice" in arg and arg["gpus"] != arg["ndevice"]:
            raise ValueError("parameters gpus and ndevice are mutually exclusive")
        for key in ("gpus", "ndevice"):  # ndevice is for vvtest backward compatibility
            if key in arg:
                if not isinstance(arg[key], int) and arg[key] is not None:
                    class_name = arg[key].__class__.__name__
                    raise ValueError(
                        f"{self.family}: expected {key}={arg[key]} to be an int, not {class_name}"
                    )
        if "nodes" in arg and "nnode" in arg and arg["nodes"] != arg["nnode"]:
            raise ValueError("parameters nodes and nnode are mutually exclusive")
        for key in ("nodes", "nnode"):  # nnode is for vvtest backward compatibility
            if key in arg:
                if not isinstance(arg[key], int) and arg[key] is not None:
                    class_name = arg[key].__class__.__name__
                    raise ValueError(
                        f"{self.family}: expected {key}={arg[key]} to be an int, not {class_name}"
                    )
                disallowed = {"cpus", "np", "gpus", "ndevice"} & arg.keys()
                if disallowed:
                    s = ", ".join(f"{key} and {_}" for _ in disallowed)
                    raise ValueError(f"parameters {s} are mutually exclusive")
        self._parameters.clear()
        self._parameters.update(arg)

    @property
    def unresolved_dependencies(self) -> list[DependencyPatterns]:
        """List of dependency patterns that must be resolved before running"""
        return self._unresolved_dependencies

    @unresolved_dependencies.setter
    def unresolved_dependencies(self, arg: list[DependencyPatterns]) -> None:
        self._unresolved_dependencies = list(arg)

    @property
    def dep_done_criteria(self) -> list[str]:
        r"""``dep_done_criteria[i]`` is the expected exit status of the ``i``\ th dependency.  This
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
            runtimes = self.load_run_stats()
            if runtimes is not None:
                self._runtimes.clear()
                self._runtimes.extend([runtimes.mean, runtimes.min, runtimes.max])
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
    def environment_modifications(self) -> list[dict[str, str]]:
        return self._environment_modifications

    @environment_modifications.setter
    def environment_modifications(self, arg: list[dict[str, str]]) -> None:
        self._environment_modifications = list(arg)

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
    def id(self) -> str:
        if not self._id:
            self._id = self.generate_id()
        assert isinstance(self._id, str)
        return self._id

    @id.setter
    def id(self, arg: str) -> None:
        assert isinstance(arg, str)
        self._id = arg

    def chain(self, start: str | None = None, anchor: str = ".git") -> str:
        dirname = os.path.dirname(start or self.file)
        while True:
            if os.path.isdir(os.path.join(dirname, anchor)):
                return os.path.relpath(self.file, dirname)
            dirname = os.path.dirname(dirname)
            if dirname == os.path.sep:
                break
        return self.path

    def generate_id(self, byte_limit: int | None = None, **kwds: str) -> str:
        """The test ID is a hash built up from the test name, parameters, and additional keywords.
        *If* the test is in a git project directory, the path relative to the project directory is
        included, otherwise the test case's path relative to the search root is hashed.  This
        latter case is potentially not unique.

        If the variable NVTEST_INCLUSIVE_CASE_ID is defined, the case id's hash will also include
        contents of auxiliary files.  This is expensive, but causes the ID to change if any of the
        test's auxiliary files change, which may be beneficial.

        """
        hasher = hashlib.sha256()
        hasher.update(self.name.encode())
        for key in sorted(self.parameters):
            hasher.update(f"{key}={stringify(self.parameters[key], float_fmt='%.16e')}".encode())
        for key in sorted(kwds):
            hasher.update(f"{key}={stringify(kwds[key], float_fmt='%.16e')}".encode())
        hasher.update(open(self.file, "rb").read())
        hasher.update(self.chain().encode())
        inclusive_case_id = boolean(os.getenv("NVTEST_INCLUSIVE_CASE_ID"))
        if inclusive_case_id:
            self._include_auxiliary_contents_in_id(hasher, byte_limit=byte_limit)
        return hasher.hexdigest()[:20]

    def _include_auxiliary_contents_in_id(
        self, hasher: "hashlib._Hash", byte_limit: int | None = None
    ) -> None:
        if byte_limit is None:
            gb: int = 1024 * 1024 * 1024
            byte_limit = int(os.getenv("NVTEST_HASH_BYTE_LIMIT", gb))
        assert byte_limit is not None
        files: list[str] = []
        if byte_limit:
            accept = lambda f: os.path.isfile(f) and os.path.getsize(f) <= byte_limit
            files.extend([asset.src for asset in self.assets if accept(asset.src)])
        else:
            hasher.update(self.chain().encode())
        files.sort()
        buffer = bytearray(4096)
        view = memoryview(buffer)
        update = hasher.update
        for file in files:
            size = os.path.getsize(file)
            with open(file, "rb") as fh:
                readinto = fh.readinto
                while size:
                    bytes_read = readinto(buffer)
                    update(view[:bytes_read])
                    size -= bytes_read

    @property
    def cpus(self) -> int:
        cpus: int = 1
        stage = config.session.stage or "run"
        if stage == "run":
            if "cpus" in self.parameters:
                cpus = int(self.parameters["cpus"])
            elif "np" in self.parameters:
                cpus = int(self.parameters["np"])
            elif "nodes" in self.parameters:
                nodes = int(self.parameters["nodes"])
                cpus = nodes * config.resource_pool.pinfo("cpus_per_node")
        return cpus

    @property
    def nodes(self) -> int:
        nodes: int = 1
        stage = config.session.stage or "run"
        if stage == "run":
            if "nodes" in self.parameters:
                nodes = int(self.parameters["nodes"])  # type: ignore
            else:
                cpus_per_node = config.resource_pool.pinfo("cpus_per_node")
                nodes = math.ceil(self.cpus / cpus_per_node)
        return nodes

    @property
    def gpus(self) -> int:
        gpus: int = 0
        stage = config.session.stage or "run"
        if stage == "run":
            if "gpus" in self.parameters:
                gpus = int(self.parameters["gpus"])  # type: ignore
            elif "ndevice" in self.parameters:
                gpus = int(self.parameters["ndevice"])  # type: ignore
            elif "nodes" in self.parameters:
                nodes = int(self.parameters["nodes"])
                gpus = nodes * config.resource_pool.pinfo("gpus_per_node")
        return gpus

    @property
    def cputime(self) -> float | int:
        return self.runtime * self.cpus

    @property
    def runtime(self) -> float | int:
        if self.runtimes[0] is None:
            return self.timeout
        return self.runtimes[0]

    @property
    def pythonpath(self):
        path = [_ for _ in os.getenv("PYTHONPATH", "").split(os.pathsep) if _.split()]
        if self.working_directory not in path:
            path.insert(0, self.working_directory)
        else:
            path.insert(0, path.pop(path.index(self.working_directory)))
        return os.pathsep.join(path)

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

    def load_run_stats(self) -> SimpleNamespace | None:
        """Return statistics kept for this test"""
        cache_dir = find_cache_dir(self.file_root)
        if cache_dir is None:
            return None
        file = os.path.join(cache_dir, f"timing/{self.id[:2]}/{self.id[2:]}.json")
        if not os.path.exists(file):
            return None
        try:
            data = json.load(open(file))
            if "timing" not in data:
                fs.force_remove(file)
                return None
            version = data["timing"].get("version")
            if version != {"major": stats_version_info[0], "minor": stats_version_info[1]}:
                fs.force_remove(file)
                return None
            return SimpleNamespace(**data["timing"]["local"])
        except Exception:
            fs.force_remove(file)
        return None

    def update_run_stats(self) -> None:
        """store runtime statistics"""
        if self.status.value not in ("success", "diffed"):
            return
        if self.duration < 0:
            return
        stats = self.load_run_stats()
        if stats is not None:
            # Welford's single pass online algorithm to update statistics
            count, mean, variance = stats.count, stats.mean, stats.variance
            delta = self.duration - mean
            mean += delta / (count + 1)
            if count > 0:
                M2 = variance * count
                delta2 = self.duration - mean
                M2 += delta * delta2
                variance = M2 / (count + 1)
            minimum = min(stats.min, self.duration)
            maximum = max(stats.max, self.duration)
        else:
            count = 0
            variance = 0.0
            mean = minimum = maximum = self.duration
        cache_dir = find_cache_dir(self.file_root, create=True)
        if cache_dir is None:
            return
        file = os.path.join(cache_dir, f"timing/{self.id[:2]}/{self.id[2:]}.json")
        local = {
            "name": self.display_name,
            "path": os.path.relpath(self.file, os.path.dirname(file)),
            "last_run": datetime.datetime.fromtimestamp(self.start).strftime("%c"),
            "count": count + 1,
            "mean": mean,
            "min": minimum,
            "max": maximum,
            "variance": variance,
        }
        try:
            fs.mkdirp(os.path.dirname(file))
            version = {"major": stats_version_info[0], "minor": stats_version_info[1]}
            with open(file, "w") as fh:
                timing = {"timing": {"version": version, "local": local}}
                json.dump(timing, fh, indent=2)
        except Exception:
            fs.force_remove(file)

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

    def modify_env(
        self, name: str, value: str | list[str] = "", *, action: str = "set", sep: str = ":"
    ) -> None:
        if isinstance(value, list):
            value = sep.join(value)
        assert isinstance(value, str)
        entry: dict[str, str] = dict(name=name, value=value, action=action, sep=sep)
        self.environment_modifications.append(entry)

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

    def describe(self) -> str:
        """Write a string describing the test case"""
        id = colorize("@*b{%s}" % self.id[:7])
        if self.mask is not None:
            string = "@*c{EXCLUDED} %s %s: %s" % (id, self.pretty_repr(), self.mask)
            return colorize(string)
        string = "%s %s %s" % (self.status.cname, id, self.pretty_repr())
        if self.duration >= 0:
            string += f" ({hhmmss(self.duration)})"
        if self.status == "skipped":
            string += " skip reason: %s" % self.status.details or "unknown"
        elif self.status == "failed":
            string += " fail reason: %s" % self.status.details or "unknown"
        elif self.status == "diffed":
            string += " diff reason: %s" % self.status.details or "unknown"
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

    def add_dependency(self, case: "TestCase", /, expected_result: str = "success") -> None:
        if case not in self.dependencies:
            self.dependencies.append(case)
            self.dep_done_criteria.append(expected_result)
            assert len(self.dependencies) == len(self.dep_done_criteria)

    def copy_sources_to_workdir(self) -> None:
        copy_all_resources: bool = config.getoption("copy_all_resources", False)
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
        lockfile = self.lockfile
        mkdirp(os.path.dirname(lockfile))
        try:
            with open(lockfile + ".tmp", "w") as fh:
                self.dump(fh)
            fs.force_copy(lockfile + ".tmp", lockfile)
        finally:
            fs.force_remove(lockfile + ".tmp")
        file = os.path.join(self.working_directory, self._lockfile)
        mkdirp(os.path.dirname(file))
        fs.force_symlink(lockfile, file)

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
    def rc_environ(self, **env: str) -> Generator[None, None, None]:
        save_env = os.environ.copy()
        variables: dict[str, str] = dict(env)
        variables.update(os.environ)
        variables.update(self.variables)
        for mod in self.environment_modifications:
            name, action, value, sep = mod["name"], mod["action"], mod["value"], mod["sep"]
            if action == "set":
                variables[name] = value
            elif action == "unset":
                os.environ.pop(name, None)
            elif action == "prepend-path":
                variables[name] = f"{value}{sep}{variables.get(name, '')}"
            elif action == "append-path":
                variables[name] = f"{variables.get(name, '')}{sep}{value}"
        vars = {}
        for group in self.resources:
            for type, instances in group.items():
                varname = type[:-1] if type[-1] == "s" else type
                ids: list[str] = [str(_["gid"]) for _ in instances]
                vars[f"{varname}_ids"] = variables[f"NVTEST_{varname.upper()}"] = ",".join(ids)
        for key, value in variables.items():
            try:
                variables[key] = value % vars
            except Exception:
                pass
        variables["PYTHONPATH"] = f"{self.pythonpath}:{variables.get('PYTHONPATH', '')}"
        variables["PATH"] = f"{self.working_directory}:{variables['PATH']}"
        try:
            os.environ.clear()
            os.environ.update(variables)
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

    def setup(self) -> None:
        if len(self.dependencies) != len(self.dep_done_criteria):
            raise ValueError("Inconsistent dependency/dep_done_criteria lists")
        logging.debug(f"Setting up {self}")
        self.work_tree = config.session.work_tree
        fs.mkdirp(self.working_directory)
        clean_out_folder(self.working_directory)
        with fs.working_dir(self.working_directory, create=True):
            self.setup_working_directory()
            self._status.set("ready" if not self.dependencies else "pending")
            for hook in plugin.hooks():
                hook.test_setup(self)
            self.save()
        logging.trace(f"Done setting up {self}")

    def setup_working_directory(self) -> None:
        copy_all_resources: bool = config.getoption("copy_all_resources", False)
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
                self.copy_sources_to_workdir()

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
        if stage == "run":
            self.setup()
            if self.unresolved_dependencies:
                raise RuntimeError("All dependencies must be resolved before running")
            with fs.working_dir(self.working_directory):
                for hook in plugin.hooks():
                    hook.test_before_run(self, stage=stage)
            self.save()

    def concatenate_logs(self) -> None:
        with open(self.logfile(), "w") as fh:
            for stage in ("setup", "run", "analyze"):
                file = self.logfile(stage)
                if os.path.exists(file):
                    fh.write(open(file).read())

    def finalize(self, stage: str = "run") -> None:
        if stage == "run":
            for hook in plugin.hooks():
                hook.test_after_run(self)
            self.update_run_stats()
        self.concatenate_logs()
        self.save()

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

    @property
    def gpus(self) -> int:
        return 0

    @property
    def nodes(self) -> int:
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


def find_cache_dir(start: str, create: bool = False) -> str | None:
    cache_dir: str
    if "NVTEST_CACHE_DIR" in os.environ:
        cache_dir = os.environ["NVTEST_CACHE_DIR"]
        if cache_dir in (os.devnull, "null"):
            return None
    else:
        dirname = start
        pjoin = os.path.join
        while True:
            if os.path.exists(pjoin(dirname, ".nvtest_cache/CACHEDIR.TAG")):
                break
            elif os.path.isdir(pjoin(dirname, ".git")) or os.path.isdir(pjoin(dirname, ".hg")):
                # cache data at the project's root
                break
            dirname = os.path.dirname(dirname)
            if dirname == os.path.sep:
                dirname = start
                break
        cache_dir = pjoin(dirname, ".nvtest_cache")
    if create:
        make_cache_dir(cache_dir)
    return cache_dir


def make_cache_dir(dirname: str) -> None:
    fs.mkdirp(dirname)
    file = os.path.join(dirname, "CACHEDIR.TAG")
    if not os.path.exists(file):
        with open(file, "w") as fh:
            fh.write("Signature: 8a477f597d28d172789f06886806bc55\n")
            fh.write("# This file is a cache directory tag automatically created by nvtest.\n")
            fh.write("# For information about cache directory tags ")
            fh.write("see https://bford.info/cachedir/\n")


class MissingSourceError(Exception):
    pass
