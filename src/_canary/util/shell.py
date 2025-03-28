# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import re
import subprocess
from contextlib import contextmanager
from typing import Generator


class Bash:
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
        args = ["set -a", f". {file}", "echo 'env<<<'", "export -p", "echo '>>>'"]
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
    shell = Bash()
    environ = shell.source_rcfile(file)
    os.environ.update(environ)


@contextmanager
def source(file: str) -> Generator[None, None, None]:
    save_env = dict(os.environ)
    shell = Bash()
    environ = shell.source_rcfile(file)
    os.environ.update(environ)
    yield
    os.environ.clear()
    os.environ.update(save_env)
