import glob
import os

from _nvtest.main import NVTestCommand
from _nvtest.util.filesystem import working_dir


def test_depends_on_one_to_one(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write("""\
import sys
import nvtest
def test():
    self = nvtest.get_instance()
    nvtest.filesystem.touchp("baz.txt")
if __name__ == '__main__':
    sys.exit(test())
""")
        with open("f2.pyt", "w") as fh:
            fh.write("""\
import os
import sys
import nvtest
nvtest.directives.depends_on('f1')
def test():
    self = nvtest.get_instance()
    assert len(self.dependencies) == 1
    assert os.path.exists(os.path.join(self.dependencies[0].exec_dir, "baz.txt"))
if __name__ == '__main__':
    sys.exit(test())
""")
        run = NVTestCommand("run")
        rc = run("-w", ".")
        if rc != 0:
            for file in glob.glob("TestResults/**/nvtest-out.txt"):
                print(open(file).read())
        assert os.path.exists("TestResults/f1")
        assert os.path.exists("TestResults/f2")
        assert rc == 0


def test_depends_on_one_to_many(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write("""\
import sys
import nvtest
def test():
    self = nvtest.get_instance()
    nvtest.filesystem.touchp("baz.txt")
if __name__ == '__main__':
    sys.exit(test())
""")
        with open("f2.pyt", "w") as fh:
            fh.write("""\
import os
import sys
import nvtest
nvtest.directives.depends_on('f1')
def test():
    self = nvtest.get_instance()
    assert len(self.dependencies) == 1
    assert os.path.exists(os.path.join(self.dependencies[0].exec_dir, "baz.txt"))
if __name__ == '__main__':
    sys.exit(test())
""")
        with open("f3.pyt", "w") as fh:
            fh.write("""\
import os
import sys
import nvtest
nvtest.directives.depends_on('f1')
def test():
    self = nvtest.get_instance()
    assert len(self.dependencies) == 1
    assert os.path.exists(os.path.join(self.dependencies[0].exec_dir, "baz.txt"))
if __name__ == '__main__':
    sys.exit(test())
""")
        run = NVTestCommand("run")
        rc = run("-w", ".")
        if rc != 0:
            for file in glob.glob("TestResults/**/nvtest-out.txt"):
                print(open(file).read())
        assert os.path.exists("TestResults/f1")
        assert os.path.exists("TestResults/f2")
        assert os.path.exists("TestResults/f3")
        assert rc == 0


def test_depends_on_glob(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write("""\
import sys
import nvtest
nvtest.directives.parameterize('a', (1, 2, 3))
def test():
    self = nvtest.get_instance()
    nvtest.filesystem.touchp(f"baz-{self.parameters.a}.txt")
if __name__ == '__main__':
    sys.exit(test())
""")
        with open("f2.pyt", "w") as fh:
            fh.write("""\
import os
import sys
import nvtest
nvtest.directives.depends_on('f1.a=2')
def test():
    self = nvtest.get_instance()
    assert len(self.dependencies) == 1
    dep = self.dependences[0]
    assert dep.parameters.a == 2
    f = os.path.join(dep.exec_dir, f"baz-{dep.parameters.a}.txt")
    assert os.path.exists(f)
if __name__ == '__main__':
    sys.exit(test())
""")


def test_depends_on_many_to_one(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write("""\
import sys
import nvtest
nvtest.directives.parameterize('a', (1, 2, 3, 4))
def test():
    self = nvtest.get_instance()
    nvtest.filesystem.touchp(f"baz-{self.parameters.a}.txt")
if __name__ == '__main__':
    sys.exit(test())
""")
        with open("f2.pyt", "w") as fh:
            fh.write("""\
import os
import sys
import nvtest
nvtest.directives.depends_on('f1.a=1', 'f1.a=3', 'f1.a=4')
def test():
    self = nvtest.get_instance()
    assert len(self.dependencies) == 3
    for dep in self.dependencies:
        assert dep.parameters.a in (1, 3, 4)
        f = os.path.join(dep.exec_dir, f"baz-{dep.parameters.a}.txt")
        assert os.path.exists(f)
if __name__ == '__main__':
    sys.exit(test())
""")
