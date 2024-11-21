import os
import sys

from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import touch
from _nvtest.util.filesystem import working_dir


def test_copy(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        touch("foo.txt")
        touch("baz.txt")
        with open("a.pyt", "w") as fh:
            fh.write("import os\n")
            fh.write("import sys\n")
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.copy('foo.txt', 'baz.txt')\n")
            fh.write("def test():\n")
            fh.write("    assert os.path.exists('./foo.txt')\n")
            fh.write("    assert os.path.exists('./baz.txt')\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        python = Executable(sys.executable)
        python("-m", "nvtest", "run", "-w", ".", fail_on_error=False)
        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            raise ValueError(f"test failed. files in working directory: {files}")


def test_copy_rename(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        touch("foo.txt")
        touch("baz.txt")
        with open("a.pyt", "w") as fh:
            fh.write("import os\n")
            fh.write("import sys\n")
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.copy(src='foo.txt', dst='foo_copy.txt')\n")
            fh.write("nvtest.directives.copy(src='baz.txt', dst='baz_copy.txt')\n")
            fh.write("def test():\n")
            fh.write("    assert os.path.exists('./foo_copy.txt')\n")
            fh.write("    assert os.path.exists('./baz_copy.txt')\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        python = Executable(sys.executable)
        python("-m", "nvtest", "run", "-w", ".", fail_on_error=False)
        if python.returncode != 0:
            files = os.listdir("./TestResults/a")
            raise ValueError(f"test failed. files in working directory: {files}")
