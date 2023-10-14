import bisect
import enum
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator
from typing import Optional
from typing import Type
from typing import Union
from typing import final

from .. import paths
from .. import plugin
from ..config import Config
from ..test.enums import Result
from ..test.partition import Partition
from ..test.testcase import TestCase
from ..util import tty
from ..util.filesystem import accessible
from ..util.filesystem import force_remove
from ..util.filesystem import mkdirp
from ..util.graph import TopologicalSorter
from ..util.tty.color import colorize
from ..finder import Finder

if TYPE_CHECKING:
    from ..config.argparsing import Parser


class _PostInit(type):
    def __call__(cls, config: Config):
        instance = type.__call__(cls, config=config)
        if post := getattr(instance, "__post_init__", None):
            post()
        return instance


class Session(metaclass=_PostInit):
    """Manages the test session

    :param InvocationParams invocation_params:
        Object containing parameters regarding the :func:`pytest.main`
        invocation.
    """

    @final
    class Mode(enum.IntEnum):
        WRITE = 1
        READ = 0
        APPEND = 2
        ANONYMOUS = 3

        @classmethod
        def _missing_(cls, name):
            name = name.upper()
            for member in cls:
                if member.name == name:
                    return member
            return None

    registry: list[Type["Session"]] = []
    exitstatus: int
    start: float
    finish: float
    config: Config
    _cases: list[TestCase]
    batches: list[Partition]
    finder: Finder

    def __init__(self, *, config: Config) -> None:
        self.config = config
        self.invocation_params = config.invocation_params
        self.option = self.config.option
        self.rel_workdir: str = None  # type: ignore

    def __init_subclass__(subclass, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        def order(cls):
            family = getattr(cls, "family", None)
            return {"config": 0, "info": 1, "test": 2, "batch": 3}.get(family, 4)

        bisect.insort(Session.registry, subclass, key=order)

    @property
    def archive_file(self) -> str:
        return os.path.join(self.dotdir, "session.json")

    @property
    def mode(self) -> Mode:
        """Possible values are

        - Mode.WRITE
          Results directory will be created and the session run within it.
        - Mode.READ
          A test results directory already exists and the session
          will be restored within it.  No new results will be written.
        - Mode.APPEND
          A test results directory already exists and the session
          will be restored within it.  New results may be written.
        - Mode.ANONYMOUS
          A test results directory will not be created.  No session state will be
          read or written.

        """
        raise NotImplementedError

    @property
    def cases(self) -> list[TestCase]:
        return self._cases

    @cases.setter
    def cases(self, arg: list[TestCase]) -> None:
        self._cases = arg
        for hook in plugin.plugins("test", "discovery"):
            for case in self._cases:
                hook(self, case)

    def __post_init__(self):
        tty.verbose("Performing test session post initialization")

        rmodes = self.Mode.READ, self.Mode.APPEND
        if self.mode in rmodes and not accessible(self.workdir):
            raise ValueError(f"Working directory {self.workdir} cannot be read")
        if self.mode in rmodes:
            self.restore()
        else:
            if self.mode == self.Mode.WRITE:
                if self.option.wipe:
                    self.remove_workdir()
                if accessible(self.workdir):
                    d = self.rel_workdir
                    raise ValueError(f"Work directory {d!r} already exists!")
                self.make_workdir()
        self.start: float = -1
        self.finish: float = -1
        tty.verbose("Done performing test session post initialization")

    def startup(self) -> None:
        tty.verbose("Starting up test session")
        self.start = time.time()
        if self.mode in (Session.Mode.WRITE, Session.Mode.APPEND):
            mkdirp(self.dotdir)
        if self.mode == Session.Mode.WRITE:
            self.dump()
        self.setup()
        for hook in plugin.plugins("session", "setup"):
            hook(self)
        tty.verbose("Done starting up test session")

    def setup(self) -> None:
        ...

    def run(self) -> int:
        raise NotImplementedError

    def teardown(self) -> None:
        for hook in plugin.plugins("session", "teardown"):
            hook(self)
        return

    @staticmethod
    def setup_parser(parser: "Parser") -> None:
        ...

    @property
    def startdir(self) -> str:
        return self.invocation_params.dir

    @property
    def workdir(self) -> str:
        if self.mode == Session.Mode.ANONYMOUS:
            raise ValueError("Anonymous sessions do not have a work directory")
        elif self.rel_workdir is None:
            raise ValueError("Work directory has not been set!")
        return os.path.join(self.startdir, self.rel_workdir)

    @workdir.setter
    def workdir(self, arg: str) -> None:
        if self.rel_workdir is not None:
            raise RuntimeError("work directory has already been set")
        if os.path.isabs(arg):
            arg = os.path.relpath(arg, self.startdir)
        self.rel_workdir = arg

    @property
    def dotdir(self) -> str:
        return os.path.join(self.workdir, ".nvtest")

    @property
    def index_file(self) -> str:
        return os.path.join(self.dotdir, "index.json")

    def cases_to_run(self) -> list[TestCase]:
        return [
            case
            for case in self.cases
            if not case.skip
            and case.result in (Result.NOTRUN, Result.NOTDONE, Result.SETUP)
        ]

    @staticmethod
    def is_workdir(path: str, ascend: bool = False) -> bool:
        path = os.path.abspath(path)
        if not ascend:
            return os.path.exists(os.path.join(path, ".nvtest", "session.json"))
        while path != os.path.sep:
            if os.path.exists(os.path.join(path, ".nvtest", "session.json")):
                return True
            path = os.path.dirname(path)
        return False

    @staticmethod
    def find_workdir(start) -> str:
        path = start
        while True:
            f = os.path.join(path, ".nvtest/session.json")
            if os.path.exists(f):
                return path
            path = os.path.dirname(path)
            if path == "/":
                raise ValueError("Could not find workdir")

    @staticmethod
    def is_batch_file(file: Union[str, None]) -> bool:
        if file is None:
            return False
        pat = "^batch.json.[0-9]+.[0-9]+$"
        dir, name = os.path.split(file)
        return Session.is_workdir(dir, ascend=True) and bool(re.search(pat, name))

    @property
    def log_level(self) -> int:
        return self.config.log_level

    def remove_workdir(self):
        if self.mode != Session.Mode.WRITE:
            mode = self.mode.name.lower()
            raise ValueError(f"Cannot remove work directory in {mode!r} mode")
        workdir_is_cwd = os.path.abspath(self.workdir) == self.invocation_params.dir
        if workdir_is_cwd:
            raise ValueError("Cannot remove work directory (workdir=PWD)")
        force_remove(self.workdir)

    def make_workdir(self):
        if os.path.exists(self.workdir):
            raise ValueError(f"Work directory {self.rel_workdir} already exists!")
        mkdirp(self.workdir)

    def dump(self, file: Optional[str] = None):
        data: dict[str, Any] = {"config": self.config.asdict()}
        data["date"] = datetime.fromtimestamp(self.start).strftime("%c")
        f: str = file or self.archive_file
        with open(f, "w") as fh:
            json.dump({"session": data}, fh, indent=2)

    def restore(self):
        with open(self.archive_file, "r") as fh:
            data = json.load(fh)
        fd = data["session"]
        self.config.restore(
            variables=fd["config"]["variables"],
            machine=fd["config"]["machine"],
            invocation_params=fd["config"]["invocation_params"],
        )

    def set_pythonpath(self, environ) -> None:
        pythonpath = [paths.prefix]
        if "PYTHONPATH" in environ:
            pythonpath.extend(environ["PYTHONPATH"].split(os.pathsep))
        if "PYTHONPATH" in os.environ:
            pythonpath.extend(os.environ["PYTHONPATH"].split(os.pathsep))
        environ["PYTHONPATH"] = os.pathsep.join(pythonpath)
        return

    @contextmanager
    def rc_environ(self) -> Generator[None, None, None]:
        save_env: dict[str, Optional[str]] = {}
        variables = dict(self.config.variables)
        self.set_pythonpath(variables)
        for var, val in variables.items():
            save_env[var] = os.environ.pop(var, None)
            os.environ[var] = val
        yield
        for var, save_val in save_env.items():
            if save_val is not None:
                os.environ[var] = save_val
            else:
                os.environ.pop(var)

    def print_text(self, text: str, force: bool = False):
        if not force and self.log_level < tty.INFO:
            return
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def print_section_header(self, label, char="=", force: bool = False):
        _, width = tty.terminal_size()
        repl = "." * tty.clen(label)
        text = f" {repl} ".center(width, char)
        self.print_text(text.replace(repl, label), force=force)

    def print_front_matter(self, force: bool = False):
        if self.option.no_header:
            return
        n = N = self.config.machine.cpu_count
        p = self.config.machine.platform
        v = self.config.python.version
        self.print_text(f"platform {p} -- Python {v}, num cores: {n}, max cores: {N}", force=force)
        self.print_text(f"rootdir: {self.invocation_params.dir}", force=force)
        self.print_text(f"work directory: {self.workdir}")
        if self.mode == self.Mode.WRITE:
            text = "search paths: {0}".format("\n  ".join(self.finder.search_paths))
            self.print_text(text)

    def print_test_results_summary(self, duration: float = -1):
        if self.log_level < tty.WARN or self.option.no_summary:
            return

        durations = getattr(self.option, "durations", None)
        if durations is not None:
            self.print_durations(int(durations))

        if duration == -1:
            finish = max(_.finish for _ in self.cases)
            start = min(_.start for _ in self.cases)
            duration = finish - start

        totals: dict[str, list[TestCase]] = {}
        for case in self.cases:
            totals.setdefault(case.result.name, []).append(case)

        nonpass = (Result.FAIL, Result.DIFF, Result.SKIP, Result.NOTDONE)
        if self.log_level > tty.INFO and len(totals):
            self.print_section_header("Short test summary info")
        elif any(r in totals for r in nonpass):
            self.print_section_header("Short test summary info")
        if self.log_level > tty.INFO and Result.PASS in totals:
            for case in totals[Result.PASS]:
                self.print_text("%s %s" % (case.result.cname, str(case)))
        nreported = 0
        for result in (Result.FAIL, Result.DIFF):
            if result not in totals:
                continue
            for case in totals[result]:
                f = case.logfile
                if f.startswith(os.getcwd()):
                    f = os.path.relpath(f)
                reasons = [case.result.reason]
                if not case.result.reason and not os.path.exists(f):
                    reasons.append("No log file found")
                else:
                    reasons.append(f"See {f}")
                reason = ". ".join(_ for _ in reasons if _.split())
                self.print_text("%s %s: %s" % (case.result.cname, str(case), reason))
                nreported += 1
            if Result.NOTDONE in totals:
                for case in totals[Result.NOTDONE]:
                    self.print_text("%s %s" % (case.result.cname, str(case)))
            if Result.SKIP in totals:
                for case in totals[Result.SKIP]:
                    cname = case.result.cname
                    reason = case.skip.reason
                    self.print_text(
                        "%s %s: Skipped due to %s" % (cname, str(case), reason)
                    )
        summary_parts = []
        for member in Result.members:
            if self.log_level <= tty.INFO and member == Result.NOTRUN:
                continue
            n = len(totals.get(member, []))
            if n:
                c = Result.colors[member]
                summary_parts.append(colorize("@%s{%d %s}" % (c, n, member.lower())))
        text = ", ".join(summary_parts)
        self.print_section_header(text + f" in {duration:.2f}s.")

    def print_durations(self, N: int) -> None:
        cases = [case for case in self.cases if case.duration > 0]
        sorted_cases = sorted(cases, key=lambda x: x.duration)
        if N > 0:
            sorted_cases = sorted_cases[-N:]
        self.print_section_header(f"Slowest {len(sorted_cases)} durations")
        for case in sorted_cases:
            self.print_text("%6.2f     %s" % (case.duration, str(case)))

    def print_testcase_summary(self) -> None:
        if self.option.no_header:
            return
        files: list[str] = list({case.file for case in self.cases})
        t = "@*{collected %d tests from %d files}" % (len(self.cases), len(files))
        self.print_text(colorize(t))
        cases_to_run = self.cases_to_run()
        max_workers = getattr(self.option, "max_workers", None)
        max_workers = max_workers or self.config.machine.cpu_count
        files = {case.file for case in cases_to_run}
        self.print_text(
            colorize(
                "@*g{running} %d test cases from %d files with %s workers"
                % (len(cases_to_run), len(files), max_workers),
            )
        )

        skipped = [case for case in self.cases if case.skip]
        skipped_reasons: dict[str, int] = {}
        for case in skipped:
            reason = case.skip.reason
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
        self.print_text(colorize("@*b{skipping} %d test cases" % len(skipped)))
        reasons = sorted(skipped_reasons, key=lambda x: skipped_reasons[x])
        for reason in reversed(reasons):
            self.print_text(f"  • {skipped_reasons[reason]} {reason.lstrip()}")
        return

    def dump_index(self) -> None:
        index: dict[str, Any] = {}

        cases: dict[str, Any] = index.setdefault("cases", {})
        for case in self.cases:
            path = None if case.skip else os.path.relpath(case.exec_dir, self.workdir)
            cases[case.id] = {
                "path": path,
                "dependencies": [d.id for d in case.dependencies],
                "skip": case.skip.reason or None,
            }

        index["batches"] = None
        if getattr(self, "batches", None) is not None:
            assert isinstance(self.batches, list)
            batches: list[list[str]] = []
            for batch in self.batches:
                case_ids = [case.id for case in batch]
                batches.append(case_ids)
            index["batches"] = batches

        mkdirp(os.path.dirname(self.index_file))
        with open(self.index_file, "w") as fh:
            json.dump({"index": index}, fh, indent=2)

    def load_index(self) -> list[TestCase]:
        if not os.path.isfile(self.index_file):
            raise ValueError(f"{self.index_file!r} not found")
        with open(self.index_file, "r") as fh:
            fd = json.load(fh)
        index = fd["index"]

        ts: TopologicalSorter = TopologicalSorter()
        tcases = index.pop("cases")
        for (id, kwds) in tcases.items():
            if not kwds["skip"]:
                ts.add(id, *kwds["dependencies"])

        cases: list[TestCase] = []
        for id in ts.static_order():
            kwds = tcases[id]
            path = os.path.join(self.workdir, kwds["path"])
            case = TestCase.load(path, cases)
            cases.append(case)

        return cases
