import _nvtest.test.case as tc
import nvtest
from _nvtest.finder import Finder
from _nvtest.resource import ResourceHandler
from _nvtest.util.filesystem import mkdirp
from _nvtest.util.filesystem import working_dir


def test_skipif(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\nnvtest.directives.skipif(True, reason='Because')")
        with open("b.pyt", "w") as fh:
            fh.write("import nvtest\nnvtest.directives.skipif(False, reason='Because')")
    finder = Finder()
    finder.add(workdir)
    assert len(finder.roots) == 1
    assert workdir in finder.roots
    finder.prepare()
    files = finder.discover()
    cases = finder.lock_and_filter(files)
    assert len(cases) == 2
    assert len([c for c in cases if not c.mask]) == 1


def test_keywords(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\nnvtest.directives.keywords('a', 'b', 'c', 'd', 'e')")
        with open("b.pyt", "w") as fh:
            fh.write("import nvtest\nnvtest.directives.keywords('e', 'f', 'g', 'h', 'i')")
    finder = Finder()
    finder.add(workdir)
    assert len(finder.roots) == 1
    assert workdir in finder.roots
    finder.prepare()
    files = finder.discover()
    cases = finder.lock_and_filter(files, keyword_expr="a and i")
    assert len([c for c in cases if not c.mask]) == 0
    cases = finder.lock_and_filter(files, keyword_expr="a and e")
    assert len([c for c in cases if not c.mask]) == 1
    cases = finder.lock_and_filter(files, keyword_expr="a or i")
    assert len([c for c in cases if not c.mask]) == 2


def test_parameterize_1(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
    finder = Finder()
    finder.add(workdir)
    assert len(finder.roots) == 1
    finder.prepare()
    files = finder.discover()
    cases = finder.lock_and_filter(files)
    assert len([c for c in cases if not c.mask]) == 3
    a, b = 0, 1
    for case in cases:
        assert case.parameters == {"a": a, "b": b}
        a += 2
        b += 2


def test_parameterize_2(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
            fh.write("nvtest.directives.parameterize('n', [10,11,12])\n")
    finder = Finder()
    finder.add(workdir)
    assert len(finder.roots) == 1
    finder.prepare()
    files = finder.discover()
    cases = finder.lock_and_filter(files)
    assert len([c for c in cases if not c.mask]) == 9
    i = 0
    for a, b in [(0, 1), (2, 3), (4, 5)]:
        for n in (10, 11, 12):
            assert cases[i].parameters == {"a": a, "b": b, "n": n}
            i += 1


def test_parameterize_3(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.parameterize('a,b', [(0,1),(2,3)], when='options=xxx')\n")
    finder = Finder()
    finder.add(workdir)
    assert len(finder.roots) == 1
    assert workdir in finder.roots
    finder.prepare()
    files = finder.discover()
    cases = finder.lock_and_filter(files, on_options=["xxx"])
    assert len([c for c in cases if not c.mask]) == 2
    cases = finder.lock_and_filter(files)
    assert len([c for c in cases if not c.mask]) == 1
    assert cases[0].parameters == {}


def test_cpu_count(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.parameterize('np', [1, 4, 8, 32])\n")
    nvtest.config.set("machine:cpus_per_node", 40)
    finder = Finder()
    finder.add(workdir)
    finder.prepare()
    files = finder.discover()
    cases = finder.lock_and_filter(files)
    assert len([c for c in cases if not c.mask]) == 4
    nvtest.config.set("machine:cpus_per_node", 2)
    cases = finder.lock_and_filter(files)
    assert len([c for c in cases if not c.mask]) == 1


def test_dep_patterns(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.depends_on('b/g[n=1]')\n")
        mkdirp("b")
        with open("b/g.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.parameterize('n', [1, 2, 3])\n")
    finder = Finder()
    finder.add(workdir)
    finder.prepare()
    files = finder.discover()
    cases = finder.lock_and_filter(files)
    assert len([c for c in cases if not c.mask]) == 4
    for case in cases:
        if case.name == "f":
            assert len(case.dependencies) == 1
            assert case.dependencies[0].name == "g.n=1"


def test_analyze(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
            fh.write("nvtest.directives.parameterize('n', [10,11,12])\n")
            fh.write("nvtest.directives.analyze()\n")
    finder = Finder()
    finder.add(workdir)
    finder.prepare()
    files = finder.discover()
    cases = finder.lock_and_filter(files)
    print(cases)
    print(vars(cases[-1]))
    assert len([c for c in cases if not c.mask]) == 10
    assert cases[-1].postflags == ["--analyze"]
    assert all(case in cases[-1].dependencies for case in cases[:-1])


def test_enable(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.enable(True, when=\"options='baz and spam'\")\n")
    finder = Finder()
    finder.add(workdir)
    finder.prepare()
    files = finder.discover()
    cases = finder.lock_and_filter(files, on_options=["baz", "spam"])
    assert len([c for c in cases if not c.mask]) == 1
    cases = finder.lock_and_filter(files, on_options=["baz"])
    assert len([c for c in cases if not c.mask]) == 0
    cases = finder.lock_and_filter(files, on_options=["spam", "baz", "foo"])
    assert len([c for c in cases if not c.mask]) == 1


def test_enable_names(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.name('foo')\n")
            fh.write("nvtest.directives.name('baz')\n")
            fh.write("nvtest.directives.name('spam')\n")
            fh.write('nvtest.directives.enable(False, when="testname=foo")\n')
    finder = Finder()
    finder.add(workdir)
    finder.prepare()
    files = finder.discover()
    cases = finder.lock_and_filter(files)
    assert len([c for c in cases if not c.mask]) == 2


def test_pyt_generator(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("test.pyt", "w") as fh:
            fh.write(
                """
import nvtest
nvtest.directives.name('baz')
nvtest.directives.analyze()
nvtest.directives.owner('me')
nvtest.directives.keywords('test', 'unit')
nvtest.directives.parameterize('np', (1, 2, 3), when="options='baz'")
nvtest.directives.parameterize('a,b,c', [(1, 11, 111), (2, 22, 222), (3, 33, 333)])
"""
            )
        rh = ResourceHandler()
        rh["test:cpu_count"] = [1, 10]
        rh["test:gpu_count"] = [0, 0]
        rh["test:node_count"] = [1, 1]

        finder = Finder()
        finder.add(".")
        finder.prepare()
        files = finder.discover()
        cases = finder.lock_and_filter(
            files,
            rh=rh,
            keyword_expr="test and unit",
            on_options=["baz"],
            owners=["me"],
            env_mods={"SPAM": "EGGS"},
        )
        assert len(cases) == 10
        assert isinstance(cases[-1], tc.TestMultiCase)
        for case in cases:
            assert not case.masked, case.mask

        # without the baz option, the `np` parameter will not be expanded so we will be left with
        # three test cases and one analyze.  The analyze will not be masked because the `np`
        # parameter is never expanded
        cases = finder.lock_and_filter(
            files,
            rh=rh,
            keyword_expr="test and unit",
            owners=["me"],
            env_mods={"SPAM": "EGGS"},
        )
        assert len(cases) == 4
        assert isinstance(cases[-1], tc.TestMultiCase)
        assert not cases[-1].masked

        # with np<3, some of the cases will be filtered
        cases = finder.lock_and_filter(
            files,
            rh=rh,
            keyword_expr="test and unit",
            on_options=["baz"],
            parameter_expr="np < 3",
            owners=["me"],
            env_mods={"SPAM": "EGGS"},
        )
        assert len(cases) == 10
        assert isinstance(cases[-1], tc.TestMultiCase)
        assert cases[-1].masked
        for case in cases[:-1]:
            assert isinstance(case, tc.TestCase)
            if case.processors == 3:
                assert case.masked
            else:
                assert not case.masked


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
        rh = ResourceHandler()
        rh["test:cpu_count"] = [1, 10]
        rh["test:gpu_count"] = [0, 0]
        rh["test:node_count"] = [1, 1]
        finder = Finder()
        finder.add(".")
        finder.prepare()
        files = finder.discover()
        cases = finder.lock_and_filter(
            files, rh=rh, keyword_expr="test and unit", on_options=["baz"]
        )
        assert len(cases) == 10
        assert isinstance(cases[-1], tc.TestMultiCase)
        for case in cases:
            assert not case.masked

        # without the baz option, the `np` parameter will not be expanded so we will be left with
        # three test cases and one analyze.  The analyze will not be masked because the `np`
        # parameter is never expanded
        cases = finder.lock_and_filter(
            files, rh=rh, keyword_expr="test and unit", env_mods={"SPAM": "EGGS"}
        )
        assert len(cases) == 4
        assert isinstance(cases[-1], tc.TestMultiCase)
        assert not cases[-1].masked

        # with np<3, some of the cases will be filtered
        cases = finder.lock_and_filter(
            files,
            rh=rh,
            keyword_expr="test and unit",
            on_options=["baz"],
            parameter_expr="np < 3",
            env_mods={"SPAM": "EGGS"},
        )
        assert len(cases) == 10
        assert isinstance(cases[-1], tc.TestMultiCase)
        assert cases[-1].masked
        for case in cases[:-1]:
            assert isinstance(case, tc.TestCase)
            if case.processors == 3:
                assert case.masked
            else:
                assert not case.masked
