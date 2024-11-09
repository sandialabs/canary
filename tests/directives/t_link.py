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
            raise ValueError(f"test failed. files in exec_dir: {files}")


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
            raise ValueError(f"test failed. files in exec_dir: {files}")


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
nvtest.directives.link('foo.txt', when={'parameters': 'a=foo'})
nvtest.directives.link('baz.txt', when='parameters="a=baz"')
def test():
    self = nvtest.get_instance()
    should_exist = 'foo.txt' if self.parameters.a == 'foo' else 'baz.txt'
    should_not_exist = 'foo.txt' if self.parameters.a == 'baz' else 'baz.txt'
    assert os.path.islink(should_exist)
    assert not os.path.islink(should_not_exist)
if __name__ == '__main__':
    sys.exit(test())
"""
            )
        python = Executable(sys.executable)
        python("-m", "nvtest", "run", "-w", ".", fail_on_error=False)
        assert os.path.exists(os.path.join(tmpdir, "TestResults/a.a=baz.b=1/baz.txt"))
        assert not os.path.exists(os.path.join(tmpdir, "TestResults/a.a=baz.b=1/foo.txt"))
        assert os.path.exists(os.path.join(tmpdir, "TestResults/a.a=foo.b=1/foo.txt"))
        assert not os.path.exists(os.path.join(tmpdir, "TestResults/a.a=foo.b=1/baz.txt"))
        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            raise ValueError(f"test failed. files in exec_dir: {files}")
