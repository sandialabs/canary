# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import sys

from _canary.util.filesystem import set_executable
from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand


def test_analyze(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f.pyt", "w") as fh:
            fh.write(
                """\
import sys
import canary
canary.directives.parameterize('a', (0, 1))
canary.directives.parameterize('b', (4, 5))
canary.directives.analyze()
def test():
    self = canary.get_instance()
    assert self.parameters.a in (0, 1)
    assert self.parameters.b in (4, 5)
    return 0
def analyze():
    self = canary.get_instance()
    assert self.parameters[('a', 'b')] == ((0, 4), (0, 5), (1, 4), (1, 5)), self.parameters[('a', 'b')]
    assert self.parameters[('b', 'a')] == ((4, 0), (5, 0), (4, 1), (5, 1)), self.parameters[('b', 'a')]
    assert self.parameters['a'] == (0, 0, 1, 1), self.parameters['a']
    assert self.parameters['b'] == (4, 5, 4, 5), self.parameters['b']
    return 0
if __name__ == '__main__':
    print("B.0", sys.argv)
    if '--analyze' in sys.argv[1:]:
        rc = analyze()
    else:
        rc = test()
    sys.exit(rc)
"""
            )
        run = CanaryCommand("run")
        cp = run("-w", ".")
        if cp.returncode != 0:
            for file in glob.glob("TestResults/**/canary-out.txt"):
                print(open(file).read())
        assert cp.returncode == 0


def test_analyze_alt_flag(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f.pyt", "w") as fh:
            fh.write(
                """\
import sys
import canary
canary.directives.parameterize('a', [0])
canary.directives.parameterize('b', [1])
canary.directives.analyze(flag='--baz')
def test():
    self = canary.get_instance()
    assert self.parameters.a == 0
    assert self.parameters.b == 1
    return 0
def analyze():
    self = canary.get_instance()
    assert self.parameters[('a', 'b')] == ((0, 1),)
    assert self.parameters[('b', 'a')] == ((1, 0),)
    assert self.parameters['a'] == (0,)
    assert self.parameters['b'] == (1,)
    return 0
if __name__ == '__main__':
    if '--baz' in sys.argv[1:]:
        rc = analyze()
    else:
        rc = test()
    sys.exit(rc)
"""
            )
        run = CanaryCommand("run")
        cp = run("-w", ".")
        if cp.returncode != 0:
            for file in glob.glob("TestResults/**/canary-out.txt"):
                print(open(file).read())
        assert cp.returncode == 0


def test_analyze_script(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f.pyt", "w") as fh:
            fh.write(
                """\
import sys
import canary
canary.directives.parameterize('a', [0])
canary.directives.parameterize('b', [1])
canary.directives.analyze(script='baz.py')
def test():
    self = canary.get_instance()
    if isinstance(self, canary.TestMultiInstance):
        assert 0, 'The script should be called!'
    assert self.parameters.a == 0
    assert self.parameters.b == 1
    return 0
if __name__ == '__main__':
    rc = test()
    sys.exit(rc)
"""
            )
        with open("baz.py", "w") as fh:
            fh.write(f"#!{sys.executable}\nimport sys\nsys.exit(0)")
        set_executable("baz.py")
        run = CanaryCommand("run")
        cp = run(".", debug=True)
        assert cp.returncode == 0
