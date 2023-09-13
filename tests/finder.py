from _nvtest.finder import Finder
from _nvtest.util.filesystem import mkdirp
from _nvtest.util.filesystem import working_dir


def test_skipif(tmpdir, config):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\nnvtest.mark.skipif(True, reason='Because')")
        with open("b.pyt", "w") as fh:
            fh.write("import nvtest\nnvtest.mark.skipif(False, reason='Because')")
    finder = Finder([workdir])
    assert len(finder.search_paths) == 1
    assert finder.search_paths[0] == workdir
    finder.discover()
    cases = finder.test_cases(config([], workdir))
    assert len(cases) == 2
    assert len([c for c in cases if not c.skip]) == 1


def test_keywords(tmpdir, config):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\nnvtest.mark.keywords('a', 'b', 'c', 'd', 'e')")
        with open("b.pyt", "w") as fh:
            fh.write("import nvtest\nnvtest.mark.keywords('e', 'f', 'g', 'h', 'i')")
    finder = Finder([workdir])
    assert len(finder.search_paths) == 1
    assert finder.search_paths[0] == workdir
    finder.discover()
    cases = finder.test_cases(config([], workdir), keyword_expr="a and i")
    assert len([c for c in cases if not c.skip]) == 0
    cases = finder.test_cases(config([], workdir), keyword_expr="a and e")
    assert len([c for c in cases if not c.skip]) == 1
    cases = finder.test_cases(config([], workdir), keyword_expr="a or i")
    assert len([c for c in cases if not c.skip]) == 2


def test_parameterize_1(tmpdir, config):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.mark.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
    finder = Finder([workdir])
    assert len(finder.search_paths) == 1
    assert finder.search_paths[0] == workdir
    finder.discover()
    cases = finder.test_cases(config([], workdir))
    assert len([c for c in cases if not c.skip]) == 3
    a, b = 0, 1
    for case in cases:
        assert case.parameters == {"a": a, "b": b}
        a += 2
        b += 2


def test_parameterize_2(tmpdir, config):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.mark.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
            fh.write("nvtest.mark.parameterize('n', [10,11,12])\n")
    finder = Finder([workdir])
    assert len(finder.search_paths) == 1
    assert finder.search_paths[0] == workdir
    finder.discover()
    cases = finder.test_cases(config([], workdir))
    assert len([c for c in cases if not c.skip]) == 9
    i = 0
    for (a, b) in [(0, 1), (2, 3), (4, 5)]:
        for n in (10, 11, 12):
            assert cases[i].parameters == {"a": a, "b": b, "n": n}
            i += 1


def test_parameterize_3(tmpdir, config):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.mark.parameterize('a,b', [(0,1),(2,3)], options='xxx')\n")
    finder = Finder([workdir])
    assert len(finder.search_paths) == 1
    assert finder.search_paths[0] == workdir
    finder.discover()
    cases = finder.test_cases(config([], workdir), on_options=["xxx"])
    assert len([c for c in cases if not c.skip]) == 2
    cases = finder.test_cases(config([], workdir))
    assert len(cases) == 1
    assert cases[0].parameters == {}


def test_cpu_count(tmpdir, config):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.mark.parameterize('np', [1, 4, 8, 32])\n")
    finder = Finder([workdir])
    finder.discover()
    cfg = config([], workdir)
    cfg.set("machine:cpu_count:40")
    cases = finder.test_cases(cfg)
    assert len([c for c in cases if not c.skip]) == 4
    cfg.set("machine:cpu_count:2")
    cases = finder.test_cases(cfg)
    assert len([c for c in cases if not c.skip]) == 1


def test_dep_patterns(tmpdir, config):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.mark.depends_on('b/g[n=1]')\n")
        mkdirp("b")
        with open("b/g.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.mark.parameterize('n', [1, 2, 3])\n")
    finder = Finder([workdir])
    finder.discover()
    cfg = config([], workdir)
    cases = finder.test_cases(cfg)
    assert len([c for c in cases if not c.skip]) == 4
    for case in cases:
        if case.name == "f":
            assert len(case.dependencies) == 1
            assert case.dependencies[0].name == "g.n=1"


def test_analyze(tmpdir, config):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.mark.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
            fh.write("nvtest.mark.parameterize('n', [10,11,12])\n")
            fh.write("nvtest.mark.analyze(True)\n")
    finder = Finder([workdir])
    finder.discover()
    cfg = config([], workdir)
    cases = finder.test_cases(cfg)
    assert len([c for c in cases if not c.skip]) == 10
    assert cases[-1].analyze == "--analyze"
    assert all(case in cases[-1].dependencies for case in cases[:-1])
