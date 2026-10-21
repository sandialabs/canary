# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Shell interaction helpers: sourcing rc-files and temporarily applying their environment.

Provides the ``Bash`` class (with ``source_rcfile``), the module-level
``source_rcfile`` helper, and the ``source`` context manager.
"""

import os
import shlex
import subprocess
import sys
from contextlib import contextmanager
from typing import Generator

#: Default time limit (seconds) for sourcing an rc file; override with
#: ``CANARY_RCFILE_TIMEOUT``.
DEFAULT_RCFILE_TIMEOUT = 300.0

#: Marker separating the rc file's own output from the environment dump.
_ENV_MARKER = b"\0__CANARY_ENV_BEGIN__\0"

# Variables that describe the transient sourcing shell, not the sourced environment.
_SKIP_VARS = frozenset(("PWD", "OLDPWD", "SHLVL", "_"))


class RcFileError(RuntimeError):
    """Raised when an rc file cannot be sourced (missing, failing, or timing out)."""


def _rcfile_timeout() -> float:
    try:
        return float(os.getenv("CANARY_RCFILE_TIMEOUT", DEFAULT_RCFILE_TIMEOUT))
    except ValueError:
        return DEFAULT_RCFILE_TIMEOUT


class Bash:
    """Helper for interacting with bash shell scripts."""

    def source_rcfile(self, file: str, timeout: float | None = None) -> dict[str, str]:
        """Source the shell script `file` and return the resulting environment.

        The environment is captured NUL-delimited from the sourcing shell (via
        Python, so values are exact: quotes, ``$``, backslashes and newlines are
        preserved verbatim).  Output is read with ``communicate`` so arbitrarily
        large rc-file output cannot deadlock on a full pipe.

        Args:
          file: The file to source
          timeout: Seconds to allow (default ``CANARY_RCFILE_TIMEOUT`` or 300).

        Returns:
          environ: The environment resulting from source `file`

        Raises:
          FileNotFoundError: If `file` does not exist.
          RcFileError: If sourcing fails (non-zero exit) or times out.
        """
        if not os.path.exists(file):
            raise FileNotFoundError(file)
        file = os.path.abspath(file)
        timeout = _rcfile_timeout() if timeout is None else timeout
        dump = (
            "import os,sys;"
            f"sys.stdout.buffer.write({_ENV_MARKER!r});"
            "sys.stdout.buffer.write(b'\\0'.join(k.encode()+b'='+v.encode() "
            "for k,v in os.environ.items() if '\\0' not in v))"
        )
        script = " ; ".join(
            [
                "set -a",
                shlex.join([".", file]),
                "__canary_rc=$?",
                "set +a",
                'if [ "$__canary_rc" -ne 0 ]; then exit "$__canary_rc"; fi',
                f"exec {shlex.quote(sys.executable)} -c {shlex.quote(dump)}",
            ]
        )
        try:
            cp = subprocess.run(
                ["bash", "--noprofile", "--norc", "-c", script],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RcFileError(f"Timed out after {timeout:g} s sourcing {file}") from None
        if cp.returncode != 0:
            err = cp.stderr.decode("utf-8", errors="replace").strip()
            raise RcFileError(
                f"Sourcing {file} failed with exit code {cp.returncode}"
                + (f": {err}" if err else "")
            )
        _, sep, payload = cp.stdout.partition(_ENV_MARKER)
        if not sep:
            raise RcFileError(f"Could not capture environment after sourcing {file}")
        environ: dict[str, str] = {}
        for entry in payload.split(b"\0"):
            name, eq, value = entry.partition(b"=")
            if not eq or not name:
                continue
            key = name.decode("utf-8", errors="surrogateescape")
            if key in _SKIP_VARS or key.startswith("__canary_"):
                continue
            environ[key] = value.decode("utf-8", errors="surrogateescape")
        return environ


def source_rcfile(file: str) -> None:
    """Source ``file`` and update ``os.environ`` with the resulting variables.

    Args:
        file: Path to the shell script to source.
    """
    shell = Bash()
    environ = shell.source_rcfile(file)
    os.environ.update(environ)


@contextmanager
def source(file: str) -> Generator[None, None, None]:
    """Context manager that sources ``file``, applies its environment, then restores the original.

    The original environment is restored even if the body raises.

    Args:
        file: Path to the shell rc-file to source.
    """
    save_env = dict(os.environ)
    try:
        shell = Bash()
        environ = shell.source_rcfile(file)
        os.environ.update(environ)
        yield
    finally:
        os.environ.clear()
        os.environ.update(save_env)
