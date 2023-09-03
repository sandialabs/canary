import bisect
import dataclasses
import enum
import json
import os
import sys
import time
from argparse import Namespace
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from typing import Generator
from typing import Iterable
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
from ..util.misc import ns2dict
from ..util.time import hhmmss
from ..util.tty.color import colorize
from .argparsing import ArgumentParser
from .argparsing import make_argument_parser


class Session:
    """Manages the test session

    :param InvocationParams invocation_params:
        Object containing parameters regarding the :func:`pytest.main`
        invocation.
    """

    @final
    @dataclasses.dataclass(frozen=True)
    class InvocationParams:
        """Holds parameters passed during :func:`nvtest.main`.

        The object attributes are read-only.

        """

        args: tuple[str, ...]
        dir: str  # The directory from which :func:`nvtest.main` was invoked

        def __init__(self, *, args: Iterable[str], dir: str) -> None:
            object.__setattr__(self, "args", tuple(args))
            object.__setattr__(self, "dir", dir)

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
    rel_workdir: str
    config: Config
    parser: ArgumentParser
    option: Namespace
    orig_invocation_params: InvocationParams
    cases: list[TestCase]
    batches: Optional[list[Partition]] = None

    def __init__(self, *, invocation_params: Optional[InvocationParams] = None) -> None:
        if invocation_params is None:
            invocation_params = self.InvocationParams(args=(), dir=os.getcwd())
        self.invocation_params = invocation_params
        self.parser: ArgumentParser = make_argument_parser()
        self.parser.add_command(self.__class__)
        self.option: Namespace = Namespace()
        self.parser.parse_args(self.invocation_params.args, namespace=self.option)
        self.config = Config()

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
        raise NotImplementedError

    def bootstrap(self):
        """Prepare the tests session by setting the session mode.  Possible values are

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
        tty.verbose("Bootstrapping test session")

        # Don't set the rel_workdir until after letting the command set up (and
        # possibly set the value of option.workdir)
        workdir = self.option.workdir or "TestResults"
        if os.path.isabs(workdir):
            workdir = os.path.relpath(workdir, self.startdir)
        self.rel_workdir = workdir

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
            self.config.do_configure(config_file=self.option.config_file)
        self.set_main_options()
        self.start: float = -1
        self.finish: float = -1
        # self.load_plugins()
        tty.verbose("Done bootstrapping test session")

    def startup(self) -> None:
        tty.verbose("Starting up test session")
        self.start = time.time()
        wmodes = Session.Mode.APPEND, Session.Mode.WRITE
        if self.mode in wmodes:
            mkdirp(self.dotdir)
            self.dump()
        self.setup()
        for name, func in plugin.plugins("session", "setup"):
            func(self)
        tty.verbose("Done starting up test session")

    def setup(self) -> None:
        ...

    def run(self) -> int:
        raise NotImplementedError

    def teardown(self) -> None:
        if self.option.timeit:
            duration = self.finish - self.start
            sys.stdout.write(f"{self.option.command} completed in {hhmmss(duration)}\n")
        return

    @staticmethod
    def setup_parser(parser: ArgumentParser) -> None:
        ...

    @property
    def startdir(self) -> str:
        return self.invocation_params.dir

    @property
    def workdir(self) -> str:
        if self.mode == Session.Mode.ANONYMOUS:
            raise ValueError("Anonymous sessions do not have a work directory")
        return os.path.join(self.startdir, self.rel_workdir)

    @property
    def dotdir(self) -> str:
        return os.path.join(self.workdir, ".nvtest")

    @property
    def index_file(self) -> str:
        return os.path.join(self.dotdir, "index.json")

    @staticmethod
    def is_workdir(path: str) -> bool:
        return os.path.exists(os.path.join(path, ".nvtest", "session.json"))

    @property
    def log_level(self) -> int:
        return self.config.log_level

    def set_main_options(self) -> None:
        args = self.option
        user_log_level = tty.default_log_level() - args.q + args.v
        log_level = max(min(user_log_level, tty.max_log_level()), tty.min_log_level())
        tty.set_log_level(log_level)
        self.config.log_level = log_level
        self.config.debug = args.debug
        for env in args.env_mods:
            self.config.variables[env.var] = env.val
        for path in args.config_mods:
            self.config.set(path)
        if args.no_user_config:
            self.config.disable_user_config = True

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

    def dump(self):
        data = {
            "args": list(self.invocation_params.args),
            "dir": self.invocation_params.dir,
            "option": ns2dict(self.option),
            "config": self.config.asdict(),
        }
        with open(self.archive_file, "w") as fh:
            json.dump({"session": data}, fh, indent=2)

    def restore(self):
        with open(self.archive_file, "r") as fh:
            data = json.load(fh)
        fd = data["session"]
        self.config.restore(fd["config"])
        ip = self.InvocationParams(args=tuple(fd["args"]), dir=fd["dir"])
        self.orig_invocation_params = ip

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
        save_env: dict[str, Union[str, None]] = {}
        variables = dict(self.config.variables)
        self.set_pythonpath(variables)
        for var, val in variables.items():
            save_env[var] = os.environ.pop(var, None)
            os.environ[var] = val
        yield
        for var, val in save_env.items():
            if val is None:
                os.environ.pop(var)
            else:
                os.environ[var] = val

    def load_builtin_plugins(self) -> None:
        import _nvtest.plugins

        path = _nvtest.plugins.__path__
        namespace = _nvtest.plugins.__name__
        plugin.load(path, namespace)

    def print_text(self, text: str):
        if self.log_level < tty.INFO:
            return
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def print_section_header(self, label, char="="):
        _, width = tty.terminal_size()
        repl = "." * tty.clen(label)
        text = f" {repl} ".center(width, char)
        self.print_text(text.replace(repl, label))

    def print_front_matter(self):
        n = N = self.config.machine.cpu_count
        p = self.config.machine.platform
        v = self.config.python.version
        self.print_text(f"platform {p} -- Python {v}, num cores: {n}, max cores: {N}")
        self.print_text(f"rootdir: {self.invocation_params.dir}")

    def print_test_results_summary(self, duration: float = -1):
        if self.log_level < tty.WARN:
            return
        if duration == -1:
            finish = max(_.finish for _ in self.cases)
            start = min(_.start for _ in self.cases)
            duration = finish - start

        totals: dict[str, list[TestCase]] = {}
        for case in self.cases:
            totals.setdefault(case.result.name, []).append(case)

        nonpass = (Result.FAIL, Result.DIFF, Result.SKIP, Result.NOTDONE)
        if self.log_level > tty.INFO and len(totals):
            tty.section("Short test summary info")
        elif any(r in totals for r in nonpass):
            tty.section("Short test summary info")
        if self.log_level > tty.INFO and Result.PASS in totals:
            for case in totals[Result.PASS]:
                self.print_text("%s %s" % (case.result.cname, str(case)))
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
        tty.section(text + f" in {duration:.2f}s.")

    def print_testcase_summary(self):
        files: list[str] = list({case.file for case in self.cases})
        t = "@*{collected %d tests from %d files}" % (len(self.cases), len(files))
        self.print_text(colorize(t))
        cases_to_run = [
            case
            for case in self.cases
            if not case.skip
            and case.result in (Result.NOTRUN, Result.NOTDONE, Result.SETUP)
        ]
        max_workers = getattr(self.option, "max_workers", -1)
        self.print_text(
            colorize(
                "@*g{running} %d test cases with %d workers"
                % (len(cases_to_run), max_workers)
            )
        )

        skipped = [case for case in self.cases if case.skip]
        skipped_reasons: dict[str, int] = {}
        for case in skipped:
            reason = case.skip.reason
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
        self.print_text(colorize("@*b{skipping} %d test cases" % len(skipped)))
        for reason, n in skipped_reasons.items():
            self.print_text(f"  - {n} {reason.lstrip()}")
        return

    def dump_index(self, **kwargs: Any) -> None:
        db: dict[str, Any] = {}
        db["date"] = datetime.now().strftime("%c")
        db.update(ns2dict(self.option))
        db.update(kwargs)
        tcases: dict[str, Any] = db.setdefault("cases", {})  # type: ignore
        for case in self.cases:
            deps: list[str] = [d.id for d in case.dependencies]
            tcases[case.id] = {
                "path": None
                if case.skip
                else os.path.relpath(case.exec_dir, self.dotdir),
                "dependencies": deps,
                "skip": case.skip.reason or None,
            }
        db["batches"] = None
        if getattr(self, "batches", None) is not None:
            assert isinstance(self.batches, list)
            batches: list[list[str]] = []
            for batch in self.batches:
                case_ids = [case.id for case in batch]
                batches.append(case_ids)
            db["batches"] = batches
        with open(self.index_file, "w") as fh:
            json.dump({"database": db}, fh, indent=2)

    def load_index(self) -> dict[str, Any]:
        if not os.path.isfile(self.index_file):
            raise ValueError(f"{self.index_file!r} not found")
        with open(self.index_file, "r") as fh:
            fd = json.load(fh)
        db = fd["database"]

        ts: TopologicalSorter = TopologicalSorter()
        tcases = db.pop("cases")
        for id, kwds in tcases.items():
            if not kwds["skip"]:
                ts.add(id, *kwds["dependencies"])

        self.cases: list[TestCase] = []
        for id in ts.static_order():
            kwds = tcases[id]
            path = os.path.join(self.dotdir, kwds["path"])
            case = TestCase.load(path, self.cases)
            self.cases.append(case)

        return db
