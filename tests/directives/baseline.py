import glob

from _nvtest.main import NVTestCommand
from _nvtest.util.filesystem import working_dir


def test_baseline(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("a.txt", "w") as fh:
            fh.write("null")
        with open("f.pyt", "w") as fh:
            fh.write("""\
import sys
import nvtest
nvtest.directives.parameterize('a', (1, 2))
nvtest.directives.baseline(src='a-out.txt', dst='a.txt', when='parameters=\"a=1\"')
def test():
    self = nvtest.get_instance()
    with open('a-out.txt', 'w') as fh:
        fh.write(f'a={self.parameters.a}')
if __name__ == '__main__':
    sys.exit(test())
""")
        run = NVTestCommand("run")
        rc = run("-w", ".")
        if rc != 0:
            for file in glob.glob("TestResults/**/nvtest-out.txt"):
                print(open(file).read())
        assert rc == 0
        with working_dir("TestResults"):
            baseline = NVTestCommand("rebaseline")
            rc = baseline(".")
        assert rc == 0
        assert open("a.txt").read() == "a=1"


def test_baseline_flag(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("a.txt", "w") as fh:
            fh.write("null")
        with open("f.pyt", "w") as fh:
            fh.write("""\
import os
import sys
import nvtest
nvtest.directives.parameterize('a', (1, 2))
nvtest.directives.baseline(flag='--baseline', when='parameters=\"a=1\"')
def test():
    self = nvtest.get_instance()
    with open('a-out.txt', 'w') as fh:
        fh.write(f'a={self.parameters.a}')
def baseline():
    self = nvtest.get_instance()
    assert self.parameters.a == 1
    dst = os.path.join(os.path.dirname(self.file), 'a.txt')
    with open(dst, 'w') as fh:
        fh.write(open('a-out.txt').read())
if __name__ == '__main__':
    if '--baseline' in sys.argv:
        rc = baseline()
    else:
        rc = test()
    sys.exit(rc)
""")
        run = NVTestCommand("run")
        rc = run("-w", ".")
        if rc != 0:
            for file in glob.glob("TestResults/**/nvtest-out.txt"):
                print(open(file).read())
        assert rc == 0
        with working_dir("TestResults"):
            baseline = NVTestCommand("rebaseline")
            rc = baseline(".")
        assert rc == 0
        assert open("a.txt").read() == "a=1"
