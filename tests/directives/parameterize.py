# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob

from _canary.main import CanaryCommand
from _canary.util.filesystem import working_dir


def test_parameterize(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f.pyt", "w") as fh:
            fh.write(
                """\
import sys
import canary
canary.directives.parameterize('a,b,c', [(1, 2, 3), (4, 5, 6)])
def test():
    self = canary.get_instance()
    a = self.parameters.a
    assert self.parameters[('a', 'b', 'c')] == (a, a + 1, a + 2)
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


def test_parameterize_prod(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f.pyt", "w") as fh:
            fh.write(
                """\
import sys
import canary
canary.directives.analyze()
canary.directives.parameterize('a,b', [('a1', 'b1'), ('a2', 'b2')])
canary.directives.parameterize('c,d', [('c1', 'd1'), ('c2', 'd2')])
def test():
    self = canary.get_instance()
    abcd = self.parameters[('a', 'b', 'c', 'd')]
    assert abcd in [
        ('a1', 'b1', 'c1', 'd1'),
        ('a1', 'b1', 'c2', 'd2'),
        ('a2', 'b2', 'c1', 'd1'),
        ('a2', 'b2', 'c2', 'd2'),
    ]
def analyze():
    self = canary.get_instance()
    assert self.parameters.a == ('a1', 'a1', 'a2', 'a2')
    assert self.parameters.b == ('b1', 'b1', 'b2', 'b2')
    assert self.parameters.c == ('c1', 'c2', 'c1', 'c2')
    assert self.parameters.d == ('d1', 'd2', 'd1', 'd2')
    abcd = self.parameters[('a', 'b', 'c', 'd')]
    assert abcd == (
        ('a1', 'b1', 'c1', 'd1'),
        ('a1', 'b1', 'c2', 'd2'),
        ('a2', 'b2', 'c1', 'd1'),
        ('a2', 'b2', 'c2', 'd2'),
    ), abcd
    bcda = self.parameters[('b', 'c', 'd', 'a')]
    assert bcda == (
        ('b1', 'c1', 'd1', 'a1'),
        ('b1', 'c2', 'd2', 'a1'),
        ('b2', 'c1', 'd1', 'a2'),
        ('b2', 'c2', 'd2', 'a2'),
    ), bcda
if __name__ == '__main__':
    if '--analyze' in sys.argv[1:]:
        rc = analyze()
    else:
        rc = test()
    sys.exit(rc)
"""
            )
        run = CanaryCommand("run")
        rc = run("-w", ".")
        for file in glob.glob("TestResults/**/canary-out.txt"):
            print(open(file).read())
        assert rc == 0
