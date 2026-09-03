# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Shell interaction helpers: sourcing rc-files and temporarily applying their environment.

Provides the ``Bash`` class (with ``source_rcfile``), the module-level
``source_rcfile`` helper, and the ``source`` context manager.
"""

import os
import re
import shlex
import subprocess
from contextlib import contextmanager
from typing import Generator


class Bash:
    """Helper for interacting with bash shell scripts."""

    def source_rcfile(self, file: str) -> dict[str, str]:
        """Source the shell script `file` and return the state before/after

        Args:
          file: The file to source

        Returns:
          environ: The environment resulting from source `file`

        """
        if not os.path.exists(file):
            raise FileNotFoundError(file)
        file = os.path.abspath(file)
        cmd = ["bash", "--noprofile", "-c"]
        args = ["set -a", shlex.join([".", file]), "echo 'env<<<'", "export -p", "echo '>>>'"]
        cmd.append(" ; ".join(args))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.wait()
        stdout = p.communicate()[0].decode("utf-8")
        match = re.search("env<<<(.*?)>>>", stdout, re.DOTALL)
        if match is None:
            return {}
        environ: dict[str, str] = {}
        skip_vars = ("PWD", "SHLVL")
        for name, value in re.findall(r"declare -x (\w+)=(.*)\n", match.group(1)):
            if name in skip_vars:
                continue
            environ[name] = value[1:-1]  # strip quotes
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

    Args:
        file: Path to the shell rc-file to source.
    """
    save_env = dict(os.environ)
    shell = Bash()
    environ = shell.source_rcfile(file)
    os.environ.update(environ)
    yield
    os.environ.clear()
    os.environ.update(save_env)
