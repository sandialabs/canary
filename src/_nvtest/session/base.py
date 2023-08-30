import dataclasses
import enum
import json
import os
import sys
import time
from argparse import Namespace
from contextlib import contextmanager
from typing import Generator
from typing import Iterable
from typing import Optional
from typing import Union
from typing import final

from .. import paths
from .. import plugin
from ..config import Config
from ..util import tty
from ..util.filesystem import accessible
from ..util.filesystem import force_remove
from ..util.filesystem import mkdirp
from ..util.misc import ns2dict
from ..util.time import hhmmss
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

    exitstatus: int
    start: float
    finish: float
    command: object
    rel_workdir: str
    config: Config
    parser: ArgumentParser
    option: Namespace
    mode: Mode
    orig_invocation_params: InvocationParams

    def __init__(self, *, invocation_params: Optional[InvocationParams] = None) -> None:
        if invocation_params is None:
            invocation_params = self.InvocationParams(args=(), dir=os.getcwd())
        self.invocation_params = invocation_params

    @property
    def archive_file(self) -> str:
        return os.path.join(self.dotdir, "session.json")

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
        self.load_builtin_plugins()

        self.parser: ArgumentParser = make_argument_parser()
        for (_, func) in plugin.plugins("session", "bootstrap"):
            func(self)
        self.option: Namespace = Namespace()
        self.parser.parse_args(self.invocation_params.args, namespace=self.option)
        self.config = Config()

        cmd_class = self.parser.get_command(self.option.command)
        if not cmd_class:
            raise ValueError(f"Unknown command {self.option.command!r}")
        self.command = cmd_class(self.config, self)
        self.mode = self.Mode(self.command.mode)

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
        tty.verbose("Done bootstrapping test session")

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

    @staticmethod
    def is_workdir(path: str) -> bool:
        return os.path.exists(os.path.join(path, ".nvtest", "session.json"))

    def set_main_options(self) -> None:
        args = self.option
        user_log_level = tty.default_log_level() - args.q + args.v
        log_level = max(min(user_log_level, tty.max_log_level()), tty.min_log_level())
        tty.set_log_level(log_level)
        self.config.log_level = log_level
        self.config.debug = args.debug
        if args.debug:
            tty.set_debug_stat(True)
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

    def startup(self) -> None:
        tty.verbose("Starting up test session")
        self.start = time.time()
        wmodes = Session.Mode.APPEND, Session.Mode.WRITE
        if self.mode in wmodes:
            mkdirp(self.dotdir)
            self.dump()
        self.command.setup()  # type: ignore
        for (name, func) in plugin.plugins("session", "setup"):
            func(self)
        tty.verbose("Done starting up test session")

    def run(self) -> int:
        return self.command.run()  # type: ignore

    def teardown(self) -> None:
        self.command.teardown()  # type: ignore
        self.finish = time.time()
        if self.option.timeit:
            duration = self.finish - self.start
            sys.stdout.write(f"{self.option.command} completed in {hhmmss(duration)}\n")
        return

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
        for (var, val) in variables.items():
            save_env[var] = os.environ.pop(var, None)
            os.environ[var] = val
        yield
        for (var, val) in save_env.items():
            if val is None:
                os.environ.pop(var)
            else:
                os.environ[var] = val

    def load_builtin_plugins(self) -> None:
        import _nvtest.plugins

        path = _nvtest.plugins.__path__
        namespace = _nvtest.plugins.__name__
        plugin.load(path, namespace)
