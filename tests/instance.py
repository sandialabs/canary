# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
from pathlib import Path

import _canary.testcase as tc
import _canary.testinst as inst
import canary
from _canary import workspace
from _canary.testexec import ExecutionSpace
from _canary.util.filesystem import mkdirp
from _canary.util.filesystem import working_dir


def generate_specs(generators, on_options=None):
    from _canary import config
    specs = config.pluginmanager.hook.canary_generate(generators=generators, on_options=on_options)
    return specs


def test_instance_deps(tmpdir):
    workdir = os.path.join(tmpdir.strpath, "src")
    with working_dir(workdir, create=True):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.analyze()\n")
            fh.write("canary.directives.parameterize('cpus', [1,2])\n")
            fh.write("canary.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
    generators = workspace.find_generators_in_path(workdir)
    specs = generate_specs(generators)
    assert len([spec for spec in specs if not spec.mask]) == 7
    work_tree = os.path.join(workdir, "tests")
    mkdirp(work_tree)
    with canary.config.override():
        lookup = {}
        for spec in specs:
            space = ExecutionSpace(Path(work_tree).parent, Path(work_tree).name)
            deps = [lookup[d.id] for d in spec.dependencies]
            case = tc.TestCase(spec=spec, workspace=space, dependencies=deps)
            lookup[case.id] = case
            case.save()
            instance = inst.from_testcase(case)
            if case.get_attribute("multicase"):
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
