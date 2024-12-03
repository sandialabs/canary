import os

import _nvtest.test.instance as inst
from _nvtest.finder import Finder
from _nvtest.util.filesystem import mkdirp
from _nvtest.util.filesystem import working_dir


def test_instance_deps(tmpdir):
    workdir = os.path.join(tmpdir.strpath, "src")
    with working_dir(workdir, create=True):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.analyze()\n")
            fh.write("nvtest.directives.parameterize('cpus', [1,2])\n")
            fh.write("nvtest.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
    finder = Finder()
    finder.add(workdir)
    assert len(finder.roots) == 1
    finder.prepare()
    files = finder.discover()
    cases = finder.lock_and_filter(files)
    assert len([c for c in cases if not c.mask]) == 7
    work_tree = os.path.join(workdir, "tests")
    mkdirp(work_tree)
    for case in cases:
        case.setup(work_tree=work_tree)
        instance = inst.load(case.working_directory)
        if isinstance(case, inst.TestMultiInstance):
            assert instance.parameters.a == (0, 2, 4, 0, 2, 4)
            assert instance.parameters.b == (1, 3, 5, 1, 3, 5)
            assert instance.parameters.cpus == (1, 1, 1, 2, 2, 2)
            assert instance.parameters["a,b,cpus"] == instance.parameters[("a", "b", "cpus")]
            assert instance.parameters["a,cpus,b"] == (
                (0, 1, 1),
                (2, 1, 3),
                (4, 1, 5),
                (0, 2, 1),
                (2, 2, 3),
                (4, 2, 5),
            )
