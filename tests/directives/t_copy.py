# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import sys
from pathlib import Path

from _canary.util.executable import Executable
from _canary.util.filesystem import working_dir


def write_file(path: str, contents: str = "") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contents)
    p.chmod(0o644)


def test_copy(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write_file("foo/foo.txt")
        write_file("foo/baz.txt")
        write_file(
            "foo/a.pyt",
            "\n".join(
                [
                    "import os",
                    "import sys",
                    "import canary",
                    "canary.directives.copy('foo.txt', 'baz.txt')",
                    "def test():",
                    "    assert os.path.exists('./foo.txt')",
                    "    assert os.path.exists('./baz.txt')",
                    "if __name__ == '__main__':",
                    "    sys.exit(test())",
                    "",
                ]
            ),
        )

        python = Executable(sys.executable)
        python("-m", "canary", "-d", "run", "-w", "foo", fail_on_error=False)

        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            print(open("./TestResults/a/canary-out.txt").read())
            raise ValueError(f"test failed. files in working directory: {files}")


def test_copy_rename(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write_file("foo/foo.txt")
        write_file("foo/baz.txt")
        write_file(
            "foo/a.pyt",
            "\n".join(
                [
                    "import os",
                    "import sys",
                    "import canary",
                    "canary.directives.copy(src='foo.txt', dst='foo_copy.txt')",
                    "canary.directives.copy(src='baz.txt', dst='baz_copy.txt')",
                    "def test():",
                    "    assert os.path.exists('./foo_copy.txt')",
                    "    assert os.path.exists('./baz_copy.txt')",
                    "if __name__ == '__main__':",
                    "    sys.exit(test())",
                    "",
                ]
            ),
        )

        python = Executable(sys.executable)
        python("-m", "canary", "-d", "run", "-w", ".", fail_on_error=False)

        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            if os.path.exists("./TestResults/a/canary-out.txt"):
                print(open("./TestResults/a/canary-out.txt").read())
            raise ValueError(f"test failed. files in working directory: {files}")
