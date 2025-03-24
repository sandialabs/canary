import glob

from _canary.main import CanaryCommand
from _canary.util.filesystem import working_dir


def test_baseline(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("a.txt", "w") as fh:
            fh.write("null")
        with open("f.pyt", "w") as fh:
            fh.write(
                """\
import sys
import canary
canary.directives.parameterize('a', (1, 2))
canary.directives.baseline(src='a-out.txt', dst='a.txt', when='parameters=\"a=1\"')
def test():
    self = canary.get_instance()
    with open('a-out.txt', 'w') as fh:
        fh.write(f'a={self.parameters.a}')
if __name__ == '__main__':
    sys.exit(test())
"""
            )
        run = CanaryCommand("run")
        rc = run("-w", ".")
        if rc != 0:
            for file in glob.glob("TestResults/**/canary-out.txt"):
                print(open(file).read())
        assert rc == 0
        with working_dir("TestResults"):
            rebaseline = CanaryCommand("rebaseline")
            rc = rebaseline(".")
        assert rc == 0
        assert open("a.txt").read() == "a=1"


def test_baseline_flag(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("a.txt", "w") as fh:
            fh.write("null")
        with open("f.pyt", "w") as fh:
            fh.write(
                """\
import os
import sys
import canary
canary.directives.parameterize('a', (1, 2))
canary.directives.baseline(flag='--baseline', when='parameters=\"a=1\"')
def test():
    self = canary.get_instance()
    with open('a-out.txt', 'w') as fh:
        fh.write(f'a={self.parameters.a}')
def baseline():
    self = canary.get_instance()
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
"""
            )
        run = CanaryCommand("run")
        rc = run("-w", ".")
        if rc != 0:
            for file in glob.glob("TestResults/**/canary-out.txt"):
                print(open(file).read())
        assert rc == 0
        with working_dir("TestResults"):
            rebaseline = CanaryCommand("rebaseline")
            rc = rebaseline(".")
        assert rc == 0
        assert open("a.txt").read() == "a=1"
