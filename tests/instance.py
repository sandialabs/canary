# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import _canary.testinstance as inst
import canary
from _canary import finder
from _canary.util.filesystem import mkdirp
from _canary.util.filesystem import working_dir


def test_instance_deps(tmpdir):
    workdir = os.path.join(tmpdir.strpath, "src")
    with working_dir(workdir, create=True):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.analyze()\n")
            fh.write("canary.directives.parameterize('cpus', [1,2])\n")
            fh.write("canary.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
    f = finder.Finder()
    f.add(workdir)
    assert len(f.roots) == 1
    f.prepare()
    files = f.discover()
    cases = finder.generate_test_cases(files)
    assert len([c for c in cases if c.status != "masked"]) == 7
    work_tree = os.path.join(workdir, "tests")
    mkdirp(work_tree)
    with canary.config.override():
        canary.config.set("session:work_tree", work_tree, scope="defaults")
        for case in cases:
            case.save()
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
