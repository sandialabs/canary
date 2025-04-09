# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob

from _canary.main import CanaryCommand
from _canary.util.filesystem import working_dir


def test_keywords(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("a.pyt", "w") as fh:
            fh.write("import sys\n")
            fh.write("import canary\n")
            fh.write("canary.directives.keywords('a', 'b', 'c')\n")
            fh.write("def test():\n")
            fh.write("    self = canary.get_instance()\n")
            fh.write("    assert self.keywords == ['a', 'b', 'c']\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        run = CanaryCommand("run")
        rc = run("-w", ".")
        assert rc == 0


def test_keywords_testname(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f.pyt", "w") as fh:
            fh.write("import sys\n")
            fh.write("import canary\n")
            fh.write("canary.directives.testname('a')\n")
            fh.write("canary.directives.testname('b')\n")
            fh.write("canary.directives.keywords('kw_a', when={'testname': 'a'})\n")
            fh.write("canary.directives.keywords('kw_b', when='testname=\"b\"')\n")
            fh.write("def test():\n")
            fh.write("    self = canary.get_instance()\n")
            fh.write("    print(f'{self.name}: {self.keywords}')\n")
            fh.write("    if self.name == 'a':\n")
            fh.write("        assert self.keywords == ['kw_a']\n")
            fh.write("    elif self.name == 'b':\n")
            fh.write("        assert self.keywords == ['kw_b']\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        run = CanaryCommand("run")
        rc = run("-w", ".")
        assert rc == 0


def test_keywords_parameters(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f.pyt", "w") as fh:
            fh.write("import sys\n")
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('a', (2, 4, 6, 8, 10))\n")
            fh.write("canary.directives.keywords('kw_2', when='parameters=\"a=2\"')\n")
            fh.write("canary.directives.keywords('kw_4', when='parameters=\"a=4\"')\n")
            fh.write("canary.directives.keywords('kw_6', when='parameters=\"a>4 and a<8\"')\n")
            fh.write("canary.directives.keywords('kw_8', when='parameters=\"a>=7\"')\n")
            fh.write("canary.directives.keywords('kw_9', 'kw_10', when='parameters=\"a>8\"')\n")
            fh.write("def test():\n")
            fh.write("    self = canary.get_instance()\n")
            fh.write("    if self.parameters.a == 2:\n")
            fh.write("        assert self.keywords == ['kw_2']\n")
            fh.write("    if self.parameters.a == 4:\n")
            fh.write("        assert self.keywords == ['kw_4']\n")
            fh.write("    if self.parameters.a == 6:\n")
            fh.write("        assert self.keywords == ['kw_6']\n")
            fh.write("    if self.parameters.a == 8:\n")
            fh.write("        assert self.keywords == ['kw_8']\n")
            fh.write("    if self.parameters.a == 10:\n")
            fh.write("        assert set(self.keywords) == {'kw_8', 'kw_9', 'kw_10'}\n")
            fh.write("if __name__ == '__main__':\n    sys.exit(test())\n")
        run = CanaryCommand("run")
        rc = run("-w", ".")
        if rc != 0:
            for file in glob.glob("TestResults/**/canary-out.txt"):
                print(open(file).read())
        assert rc == 0
