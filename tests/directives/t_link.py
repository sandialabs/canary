# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import os
import sys
from pathlib import Path

from _canary.util.executable import Executable
from _canary.util.filesystem import touch
from _canary.util.filesystem import working_dir


def test_link(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        touch("foo.txt")
        touch("baz.txt")
        with open("a.pyt", "w") as fh:
            fh.write("import os\n")
            fh.write("import sys\n")
            fh.write("import canary\n")
            fh.write("canary.directives.link('foo.txt', 'baz.txt')\n")
            fh.write("def test():\n")
            fh.write("    assert os.path.islink('./foo.txt')\n")
            fh.write("    assert os.path.islink('./baz.txt')\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        python = Executable(sys.executable)
        python("-m", "canary", "run", "-w", ".", fail_on_error=False)
        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            raise ValueError(f"test failed. files in working directory: {files}")


def test_link_rename(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        touch("foo.txt")
        touch("baz.txt")
        with open("a.pyt", "w") as fh:
            fh.write("import os\n")
            fh.write("import sys\n")
            fh.write("import canary\n")
            fh.write("canary.directives.link(src='foo.txt', dst='foo_link.txt')\n")
            fh.write("canary.directives.link(src='baz.txt', dst='baz_link.txt')\n")
            fh.write("def test():\n")
            fh.write("    assert os.path.islink('./foo_link.txt')\n")
            fh.write("    assert os.path.islink('./baz_link.txt')\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        python = Executable(sys.executable)
        python("-m", "canary", "run", "-w", ".", fail_on_error=False)
        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            raise ValueError(f"test failed. files in working directory: {files}")


def test_link_rename_rel(tmpdir):
    wd = os.path.join(tmpdir.strpath, "test_link_rename_rl")
    with working_dir(wd, create=True):
        touch("../foo.txt")
        touch("../baz.txt")
        with open("a.pyt", "w") as fh:
            fh.write("import os\n")
            fh.write("import sys\n")
            fh.write("import canary\n")
            fh.write("canary.directives.link(src='../foo.txt', dst='foo_link.txt')\n")
            fh.write("canary.directives.link(src='../baz.txt', dst='baz_link.txt')\n")
            fh.write("def test():\n")
            fh.write("    assert os.path.islink('./foo_link.txt')\n")
            fh.write("    assert os.path.islink('./baz_link.txt')\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        python = Executable(sys.executable)
        python("-m", "canary", "run", "-w", ".", fail_on_error=False)
        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            raise ValueError(f"test failed. files in working directory: {files}")


def test_link_rename_rel_vvt(tmpdir):
    wd = os.path.join(tmpdir.strpath, "test_link_rename_rl")
    with working_dir(wd, create=True):
        touch("../foo.txt")
        touch("../baz.txt")
        with open("a.vvt", "w") as fh:
            fh.write("# VVT: link (rename) : ../foo.txt,foo_link.txt\n")
            fh.write("# VVT: link (rename) : ../baz.txt,baz_link.txt\n")
            fh.write("import os\n")
            fh.write("import sys\n")
            fh.write("def test():\n")
            fh.write("    assert os.path.islink('./foo_link.txt')\n")
            fh.write("    assert os.path.islink('./baz_link.txt')\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        python = Executable(sys.executable)
        python("-m", "canary", "run", "-w", ".", fail_on_error=False)
        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            print(open("./TestResults/a/canary-out.txt").read())
            raise ValueError(f"test failed. files in working directory: {files}")


def test_link_when(tmpdir):
    dir = Path(__file__).parent
    f = dir / "../data/generators/link_when.pyt"
    assert f.exists()
    with working_dir(tmpdir.strpath, create=True):

        def txtfiles(d):
            basename = os.path.basename
            files = glob.glob(os.path.join(tmpdir, d, "*.txt"))
            return sorted([basename(f) for f in files if not basename(f).startswith("canary-")])

        python = Executable(sys.executable)
        python("-m", "canary", "run", str(f), fail_on_error=False)
        p = python("-m", "canary", "location", "link_when.a=link_when_1.b=1", stdout=str)
        assert txtfiles(p.out.strip()) == ["link_when_1.txt"]
        p = python("-m", "canary", "location", "link_when.a=link_when_1.b=2", stdout=str)
        assert txtfiles(p.out.strip()) == ["link_when_1-b2.txt"]
        p = python("-m", "canary", "location", "link_when.a=link_when_2.b=1", stdout=str)
        assert txtfiles(p.out.strip()) == ["link_when_2.txt"]
        p = python("-m", "canary", "location", "link_when.a=link_when_2.b=2", stdout=str)
        assert txtfiles(p.out.strip()) == ["link_when_2-b2.txt"]

        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            raise ValueError(f"test failed. files in working directory: {files}")
