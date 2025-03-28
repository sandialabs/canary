# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import os
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TextIO

from . import logging

IOType = type[str] | TextIO | Path | str


class Executable:
    """Create a callable object for the executable ``name``

    Args:
      name: The path to an executable which is run when called.  If ``name`` is not an absolute or
        relative path on the filesystem, the path to the executable is looked for on ``PATH``.

    Examples:

      >>> ls = Executable("ls")
      >>> result = ls("-la", stdout=os.devnull)
      >>> result.returncode
      0

    """

    def __init__(self, name: str | Path) -> None:
        self.file = Executable.find(name)
        self.default_args: list[str] = []
        self.default_env: dict[str, str] = {}
        self.returncode: int = -1

    @staticmethod
    def find(name: str | Path) -> Path:
        """Find the path to the command ``name``"""
        if is_executable(name):
            return Path(name).absolute()
        paths = [Path(p) for p in os.getenv("PATH", "").split(os.pathsep) if p.split()]
        for path in paths:
            file = path.joinpath(name)
            if is_executable(file):
                return file
        raise FileNotFoundError(name)

    @property
    def command(self) -> str:
        """The command-line string.

        Returns:
            str: The executable and default arguments
        """
        return str(self.file)

    @property
    def name(self) -> str:
        """The executable name.

        Returns:
            str: The basename of the executable
        """
        return self.file.name

    @property
    def path(self) -> Path:
        """The path to the executable.

        Returns:
            str: The path to the executable
        """
        return self.file

    def add_default_args(self, *args: str) -> None:
        """Add flags to this executable's default arguments"""
        self.default_args.extend(map(str, args))

    def add_default_env(self, *args: dict[str, str], **kwargs: str) -> None:
        """Add variables to this executable's runtime environment

        Args:
          args: A dictionary of environment variables
          kwargs: Environment variables

        """
        if args:
            self.default_env.update(args[0])
        if kwargs:
            self.default_env.update(kwargs)

    def __call__(
        self,
        *args_in: str,
        stdout: IOType | None = None,
        stderr: IOType | None = None,
        output: IOType | None = None,
        error: IOType | None = None,
        env: dict[str, str] | None = None,
        expected_returncode: int = 0,
        fail_on_error: bool = True,
        timeout: float = -1.0,
        verbose: bool = False,
    ) -> "Result":
        """Run this executable in a subprocess.

        Args:
          *args_in: Command-line arguments to the executable to run

        Keyword Args:
          env: The environment to run the executable with
          fail_on_error: Raise an exception if the subprocess returns an error. Default is True.
            The return code is available as ``exe.returncode``
          expected_returncode: Expected returncode.  If ``expected_returncode < 0``, this process
            will not raise an exception even if ``fail_on_error`` is set to ``True``
          stdout: Where to send stdout
          stderr: Where to send stderr
          output: Alias for stdout
          error: Alias for stderr
          verbose: Write the command line to ``output``

        Returns:
          result: A Result dataclass with the following members:
            result.cmd: The command line
            result.returncode: Exit code from subprocess
            result.out, result.err: See discussion below

        Accepted values for stdout and stderr:

        * python streams, e.g. open Python file objects, or ``os.devnull``
        * filenames, which will be automatically opened for writing
        * ``str``, as in the Python string type. If you set these to ``str``, result.out and
          result.err will contain the processes stdout and stderr, respectively, as strings.

        """
        self.returncode = -1

        args: list[str] = [self.command]
        args.extend(self.default_args)
        args.extend(map(str, args_in))

        env = env or dict(os.environ)
        env.update(self.default_env)

        result = Result(shlex.join(args))

        if verbose:
            logging.info(f"Command line: {result.cmd}")

        try:
            f1: _StreamHandler
            f2: _StreamHandler
            with _StreamHandler(stdout or output) as f1, _StreamHandler(stderr or error) as f2:
                proc = subprocess.Popen(
                    args, env=env, stdout=f1.stream, stderr=f2.stream, start_new_session=True
                )
                start = time.monotonic()
                while True:
                    if proc.poll() is not None:
                        break
                    if timeout > 0 and time.monotonic() - start > timeout:
                        proc.kill()
                        raise CommandTimedOutError
                    time.sleep(0.05)
            result.returncode = self.returncode = proc.returncode
            result.out = f1.getvalue()
            result.err = f2.getvalue()
            if fail_on_error and result.returncode != expected_returncode:
                raise ProcessError(
                    f"Command exited with status {self.returncode}: {shlex.join(args)}"
                )
            return result

        except OSError as e:
            result.returncode = self.returncode = e.errno  # type: ignore
            msg = f"{self.file}: {e.strerror}"
            if fail_on_error:
                raise ProcessError(msg)
            logging.error(msg)

        except CommandTimedOutError as e:
            result.returncode = self.returncode = 101
            msg = f"{e}\nExecution timed out when invoking command: {result.cmd}"
            if fail_on_error:
                raise TimeoutError(msg) from None
            logging.error(msg)

        except Exception as e:
            result.returncode = self.returncode = 1
            msg = f"{e}\nUnknown failure occurred when invoking command: {result.cmd}"
            if fail_on_error:
                raise ProcessError(msg)
            logging.error(msg)

        return result

    def __eq__(self, other):
        return self.path == other.path

    def __neq__(self, other):
        return not (self == other)

    def __hash__(self):
        return hash((type(self),) + (self.command,))

    def __repr__(self):
        return f"<exe: {self.command}>"

    def __str__(self):
        return f"<exe: {self.command}>"


def is_executable(path: str | Path) -> bool:
    f = Path(path)
    return f.exists() and os.access(f, os.X_OK)


class _StreamHandler:
    def __init__(self, fp: IOType | None) -> None:
        self.name: str
        self.stream: TextIO | tempfile._TemporaryFileWrapper | None = None
        self.owned: bool = False
        self.temporary: bool = False
        self.value: str | None = None
        if fp is None:
            self.name = "<None>"
        elif hasattr(fp, "fileno"):
            if fp.closed:  # type: ignore
                raise TypeError(f"{fp}: file must be opened for writing")
            self.stream = fp  # type: ignore
            self.name = getattr(self.stream, "name", "<file>")
        elif fp is str:
            self.temporary = self.owned = True
            self.stream = tempfile.NamedTemporaryFile(mode="w+")
            self.name = self.stream.name
        elif isinstance(fp, (str, Path)):
            self.owned = True
            self.stream = open(fp, "w")
            self.name = self.stream.name
        else:
            raise TypeError(f"{fp}: unknown input argument type: {type(fp).__class__.__name__}")

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_value, ex_traceback):
        if self.temporary:
            self.stream.seek(0)
            self.value = self.stream.read()
        if self.owned:
            self.stream.close()

    def getvalue(self) -> str | None:
        return self.value


@dataclasses.dataclass
class Result:
    cmd: str
    returncode: int = -1
    out: str | None = None
    err: str | None = None

    def get_output(self) -> str:
        if self.out is None:
            raise ValueError("No output string")
        assert isinstance(self.out, str)
        return self.out.strip()

    def get_error(self) -> str:
        if self.err is None:
            raise ValueError("No error string")
        assert isinstance(self.err, str)
        return self.err.strip()


class ProcessError(Exception):
    pass


class CommandTimedOutError(Exception):
    pass
