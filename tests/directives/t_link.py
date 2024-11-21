import glob
import os
import sys

from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import touch
from _nvtest.util.filesystem import working_dir


def test_link(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        touch("foo.txt")
        touch("baz.txt")
        with open("a.pyt", "w") as fh:
            fh.write("import os\n")
            fh.write("import sys\n")
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.link('foo.txt', 'baz.txt')\n")
            fh.write("def test():\n")
            fh.write("    assert os.path.islink('./foo.txt')\n")
            fh.write("    assert os.path.islink('./baz.txt')\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        python = Executable(sys.executable)
        python("-m", "nvtest", "run", "-w", ".", fail_on_error=False)
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
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.link(src='foo.txt', dst='foo_link.txt')\n")
            fh.write("nvtest.directives.link(src='baz.txt', dst='baz_link.txt')\n")
            fh.write("def test():\n")
            fh.write("    assert os.path.islink('./foo_link.txt')\n")
            fh.write("    assert os.path.islink('./baz_link.txt')\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        python = Executable(sys.executable)
        python("-m", "nvtest", "run", "-w", ".", fail_on_error=False)
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
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.link(src='../foo.txt', dst='foo_link.txt')\n")
            fh.write("nvtest.directives.link(src='../baz.txt', dst='baz_link.txt')\n")
            fh.write("def test():\n")
            fh.write("    assert os.path.islink('./foo_link.txt')\n")
            fh.write("    assert os.path.islink('./baz_link.txt')\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        python = Executable(sys.executable)
        python("-m", "nvtest", "run", "-w", ".", fail_on_error=False)
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
        python("-m", "nvtest", "run", "-w", ".", fail_on_error=False)
        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            print(open("./TestResults/a/nvtest-out.txt").read())
            raise ValueError(f"test failed. files in working directory: {files}")


def test_link_when(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        touch("foo.txt")
        touch("baz.txt")
        with open("a.pyt", "w") as fh:
            fh.write(
                """\
import os
import sys
import nvtest
nvtest.directives.parameterize('a', ('baz', 'foo'))
nvtest.directives.parameterize('b', (1, 2))
nvtest.directives.link('foo.txt', when={'parameters': 'a=foo and b=1'})
nvtest.directives.link('baz.txt', when='parameters="a=baz and b=1"')
nvtest.directives.link(src='foo.txt', dst='foo-b2.txt', when={'parameters': 'a=foo and b=2'})
nvtest.directives.link(src='baz.txt', dst='baz-b2.txt', when='parameters="a=baz and b=2"')
def test():
    self = nvtest.get_instance()
    if self.parameters[('a', 'b')] == ('foo', 1):
        assert os.path.islink('foo.txt')
    elif self.parameters[('a', 'b')] == ('baz', 1):
        assert os.path.islink('baz.txt')
    elif self.parameters[('a', 'b')] == ('foo', 2):
        assert os.path.islink('foo-b2.txt')
    elif self.parameters[('a', 'b')] == ('baz', 2):
        assert os.path.islink('baz-b2.txt')
if __name__ == '__main__':
    sys.exit(test())
"""
            )

        def txtfiles(d):
            basename = os.path.basename
            files = glob.glob(os.path.join(tmpdir, d, "*.txt"))
            return sorted([basename(f) for f in files if not basename(f).startswith("nvtest-")])

        python = Executable(sys.executable)
        python("-m", "nvtest", "run", "-w", ".", fail_on_error=False)
        assert txtfiles("TestResults/a.a=foo.b=1") == ["foo.txt"]
        assert txtfiles("TestResults/a.a=foo.b=2") == ["foo-b2.txt"]
        assert txtfiles("TestResults/a.a=baz.b=1") == ["baz.txt"]
        assert txtfiles("TestResults/a.a=baz.b=2") == ["baz-b2.txt"]

        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            raise ValueError(f"test failed. files in working directory: {files}")
