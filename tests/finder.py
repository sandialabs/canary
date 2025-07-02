# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import _canary.config as config
import _canary.testcase as tc
import canary
from _canary import finder
from _canary.util.filesystem import mkdirp
from _canary.util.filesystem import working_dir


def mask(
    cases,
    *,
    keyword_exprs=None,
    parameter_expr=None,
    owners=None,
    regex=None,
    case_specs=None,
    start=None,
):
    from _canary.plugins.builtin.mask import canary_testsuite_mask

    canary_testsuite_mask(
        cases,
        keyword_exprs=keyword_exprs,
        parameter_expr=parameter_expr,
        owners=owners,
        regex=regex,
        case_specs=case_specs,
        start=start,
        ignore_dependencies=False,
    )


def test_skipif(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\ncanary.directives.skipif(True, reason='Because')")
        with open("b.pyt", "w") as fh:
            fh.write("import canary\ncanary.directives.skipif(False, reason='Because')")
    f = finder.Finder()
    f.add(workdir)
    assert len(f.roots) == 1
    assert workdir in f.roots
    f.prepare()
    files = f.discover()
    cases = finder.generate_test_cases(files)
    assert len(cases) == 2
    assert len([c for c in cases if not c.masked()]) == 1


def test_keywords(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\ncanary.directives.keywords('a', 'b', 'c', 'd', 'e')")
        with open("b.pyt", "w") as fh:
            fh.write("import canary\ncanary.directives.keywords('e', 'f', 'g', 'h', 'i')")
    f = finder.Finder()
    f.add(workdir)
    assert len(f.roots) == 1
    assert workdir in f.roots
    f.prepare()
    files = f.discover()
    cases = finder.generate_test_cases(files)
    mask(cases, keyword_exprs=["a and i"])
    assert len([c for c in cases if not c.masked()]) == 0
    cases = finder.generate_test_cases(files)
    mask(cases, keyword_exprs=["a and e"])
    assert len([c for c in cases if not c.masked()]) == 1
    cases = finder.generate_test_cases(files)
    mask(cases, keyword_exprs=["a or i"])
    assert len([c for c in cases if not c.masked()]) == 2


def test_parameterize_1(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
    f = finder.Finder()
    f.add(workdir)
    assert len(f.roots) == 1
    f.prepare()
    files = f.discover()
    cases = finder.generate_test_cases(files)
    assert len([c for c in cases if not c.masked()]) == 3
    a, b = 0, 1
    for case in cases:
        assert case.parameters == {"a": a, "b": b}
        a += 2
        b += 2


def test_parameterize_2(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
            fh.write("canary.directives.parameterize('n', [10,11,12])\n")
    f = finder.Finder()
    f.add(workdir)
    assert len(f.roots) == 1
    f.prepare()
    files = f.discover()
    cases = finder.generate_test_cases(files)
    assert len([c for c in cases if not c.masked()]) == 9
    i = 0
    for a, b in [(0, 1), (2, 3), (4, 5)]:
        for n in (10, 11, 12):
            assert cases[i].parameters == {"a": a, "b": b, "n": n}
            i += 1


def test_parameterize_3(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('a,b', [(0,1),(2,3)], when='options=xxx')\n")
    f = finder.Finder()
    f.add(workdir)
    assert len(f.roots) == 1
    assert workdir in f.roots
    f.prepare()
    files = f.discover()
    cases = finder.generate_test_cases(files, on_options=["xxx"])
    assert len([c for c in cases if not c.masked()]) == 2
    cases = finder.generate_test_cases(files)
    assert len([c for c in cases if not c.masked()]) == 1
    assert cases[0].parameters == {}


def test_cpu_count(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('cpus', [1, 4, 8, 32])\n")
    with canary.config.override():
        canary.config.resource_pool.fill_uniform(node_count=1, cpus_per_node=42)
        f = finder.Finder()
        f.add(workdir)
        f.prepare()
        files = f.discover()
        cases = finder.generate_test_cases(files)
        assert len([c for c in cases if not c.masked()]) == 4
    with canary.config.override():
        canary.config.resource_pool.fill_uniform(node_count=1, cpus_per_node=2)
        cases = finder.generate_test_cases(files)
        mask(cases)
        assert len([c for c in cases if not c.masked()]) == 1


def test_dep_patterns(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.depends_on('b/g[n=1]')\n")
        mkdirp("b")
        with open("b/g.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('n', [1, 2, 3])\n")
    f = finder.Finder()
    f.add(workdir)
    f.prepare()
    files = f.discover()
    cases = finder.generate_test_cases(files)
    assert len([c for c in cases if not c.masked()]) == 4
    for case in cases:
        if case.name == "f":
            assert len(case.dependencies) == 1
            assert case.dependencies[0].name == "g.n=1"


def test_analyze(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
            fh.write("canary.directives.parameterize('n', [10,11,12])\n")
            fh.write("canary.directives.generate_composite_base_case()\n")
    f = finder.Finder()
    f.add(workdir)
    f.prepare()
    files = f.discover()
    cases = finder.generate_test_cases(files)
    assert len([c for c in cases if not c.masked()]) == 10
    assert all(case in cases[-1].dependencies for case in cases[:-1])


def test_enable(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.enable(True, when=\"options='baz and spam'\")\n")
    f = finder.Finder()
    f.add(workdir)
    f.prepare()
    files = f.discover()
    cases = finder.generate_test_cases(files, on_options=["baz", "spam"])
    assert len([c for c in cases if not c.masked()]) == 1
    cases = finder.generate_test_cases(files, on_options=["baz"])
    assert len([c for c in cases if not c.masked()]) == 0
    cases = finder.generate_test_cases(files, on_options=["spam", "baz", "foo"])
    assert len([c for c in cases if not c.masked()]) == 1


def test_enable_names(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.name('foo')\n")
            fh.write("canary.directives.name('baz')\n")
            fh.write("canary.directives.name('spam')\n")
            fh.write('canary.directives.enable(False, when="testname=foo")\n')
    f = finder.Finder()
    f.add(workdir)
    f.prepare()
    files = f.discover()
    cases = finder.generate_test_cases(files)
    assert len([c for c in cases if not c.masked()]) == 2


def test_pyt_generator(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("test.pyt", "w") as fh:
            fh.write(
                """
import canary
canary.directives.name('baz')
canary.directives.generate_composite_base_case()
canary.directives.owner('me')
canary.directives.keywords('test', 'unit')
canary.directives.parameterize('cpus', (1, 2, 3), when="options='baz'")
canary.directives.parameterize('a,b,c', [(1, 11, 111), (2, 22, 222), (3, 33, 333)])
"""
            )
        with config.override():
            config.test.cpu_count = (1, 10)
            config.test.gpu_count = (0, 0)
            config.test.node_count = (1, 1)

            f = finder.Finder()
            f.add(".")
            f.prepare()
            files = f.discover()
            cases = finder.generate_test_cases(files, on_options=["baz"])
            mask(cases, keyword_exprs=["test and unit"], owners=["me"])
            assert len(cases) == 10
            assert isinstance(cases[-1], tc.TestMultiCase)
            for case in cases:
                assert not case.masked(), f"{case}: {case.status}"

            # without the baz option, the `cpus` parameter will not be expanded so we will be left with
            # three test cases and one analyze.  The analyze will not be masked because the `cpus`
            # parameter is never expanded
            cases = finder.generate_test_cases(files)
            mask(cases, keyword_exprs=["test and unit"], owners=["me"])
            assert len(cases) == 4
            assert isinstance(cases[-1], tc.TestMultiCase)
            assert not cases[-1].masked()

            # with cpus<3, some of the cases will be filtered
            cases = finder.generate_test_cases(files, on_options=["baz"])
            mask(cases, keyword_exprs=["test and unit"], parameter_expr="cpus < 3", owners=["me"])
            assert len(cases) == 10
            assert isinstance(cases[-1], tc.TestMultiCase)
            assert cases[-1].masked()
            for case in cases[:-1]:
                assert isinstance(case, tc.TestCase)
                if case.cpus == 3:
                    assert case.masked()
                else:
                    assert not case.masked()


def test_vvt_generator(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("test.vvt", "w") as fh:
            fh.write(
                """
# VVT: name: baz
# VVT: analyze : --analyze
# VVT: keywords: test unit
# VVT: parameterize (options=baz) : np=1 2 3
# VVT: parameterize : a,b,c=1,11,111 2,22,222 3,33,333
"""
            )
        with config.override():
            config.test.cpu_count = (1, 10)
            config.test.gpu_count = (0, 0)
            config.test.node_count = (1, 1)

            f = finder.Finder()
            f.add(".")
            f.prepare()
            files = f.discover()
            cases = finder.generate_test_cases(files, on_options=["baz"])
            mask(cases, keyword_exprs=["test and unit"])
            assert len(cases) == 10
            assert isinstance(cases[-1], tc.TestMultiCase)
            for case in cases:
                assert not case.masked()

            # without the baz option, the `np` parameter will not be expanded so we will be left with
            # three test cases and one analyze.  The analyze will not be masked because the `np`
            # parameter is never expanded
            cases = finder.generate_test_cases(files)
            mask(cases, keyword_exprs=["test and unit"])
            assert len(cases) == 4
            assert isinstance(cases[-1], tc.TestMultiCase)
            assert not cases[-1].masked()

            # with np<3, some of the cases will be filtered
            cases = finder.generate_test_cases(files, on_options=["baz"])
            mask(cases, keyword_exprs=["test and unit"], parameter_expr="np < 3")
            assert len(cases) == 10
            assert isinstance(cases[-1], tc.TestMultiCase)
            assert cases[-1].masked()
            for case in cases[:-1]:
                assert isinstance(case, tc.TestCase)
                if case.cpus == 3:
                    assert case.masked()
                else:
                    assert not case.masked()
