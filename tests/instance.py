import os

from _nvtest.finder import Finder
from _nvtest.test.case import AnalyzeTestCase
from _nvtest.test.instance import TestInstance
from _nvtest.util.filesystem import working_dir


def test_instance_deps(tmpdir):
    workdir = os.path.join(tmpdir.strpath, "src")
    with working_dir(workdir, create=True):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.analyze()\n")
            fh.write("nvtest.directives.parameterize('np', [1,2])\n")
            fh.write("nvtest.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
    finder = Finder()
    finder.add(workdir)
    assert len(finder.roots) == 1
    finder.prepare()
    files = finder.discover()
    cases = finder.freeze(files)
    assert len([c for c in cases if not c.mask]) == 7
    for case in cases:
        case.setup(exec_root=os.path.join(workdir, "tests"))
        instance = TestInstance.from_case(case)
        if isinstance(case, AnalyzeTestCase):
            assert instance.parameters.a == (0, 2, 4, 0, 2, 4)
            assert instance.parameters.b == (1, 3, 5, 1, 3, 5)
            assert instance.parameters.np == (1, 1, 1, 2, 2, 2)
