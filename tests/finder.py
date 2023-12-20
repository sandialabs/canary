import nvtest
from _nvtest.finder import Finder
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
    tree = finder.populate()
    cases = finder.freeze(tree)
    assert len(cases) == 2
    assert len([c for c in cases if not c.masked]) == 1


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
    tree = finder.populate()
    cases = finder.freeze(tree, keyword_expr="a and i")
    assert len([c for c in cases if not c.masked]) == 0
    cases = finder.freeze(tree, keyword_expr="a and e")
    assert len([c for c in cases if not c.masked]) == 1
    cases = finder.freeze(tree, keyword_expr="a or i")
    assert len([c for c in cases if not c.masked]) == 2


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
    tree = finder.populate()
    cases = finder.freeze(tree)
    assert len([c for c in cases if not c.masked]) == 3
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
    tree = finder.populate()
    cases = finder.freeze(tree)
    assert len([c for c in cases if not c.masked]) == 9
    i = 0
    for (a, b) in [(0, 1), (2, 3), (4, 5)]:
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
    tree = finder.populate()
    cases = finder.freeze(tree, on_options=["xxx"])
    assert len([c for c in cases if not c.masked]) == 2
    cases = finder.freeze(tree)
    assert len([c for c in cases if not c.masked]) == 1
    assert cases[0].parameters == {}


def test_cpu_count(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.parameterize('np', [1, 4, 8, 32])\n")
    nvtest.config.set("machine:cpu_count", 40)
    finder = Finder()
    finder.add(workdir)
    finder.prepare()
    tree = finder.populate()
    cases = finder.freeze(tree)
    assert len([c for c in cases if not c.masked]) == 4
    nvtest.config.set("machine:cpu_count", 2)
    cases = finder.freeze(tree)
    assert len([c for c in cases if not c.masked]) == 1


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
    tree = finder.populate()
    cases = finder.freeze(tree)
    assert len([c for c in cases if not c.masked]) == 4
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
            fh.write("nvtest.directives.analyze(True)\n")
    finder = Finder()
    finder.add(workdir)
    finder.prepare()
    tree = finder.populate()
    cases = finder.freeze(tree)
    assert len([c for c in cases if not c.masked]) == 10
    assert cases[-1].analyze == "--analyze"
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
    tree = finder.populate()
    cases = finder.freeze(tree, on_options=["baz", "spam"])
    assert len([c for c in cases if not c.masked]) == 1
    cases = finder.freeze(tree, on_options=["baz"])
    assert len([c for c in cases if not c.masked]) == 0
    cases = finder.freeze(tree, on_options=["spam", "baz", "foo"])
    assert len([c for c in cases if not c.masked]) == 1


def test_enable_names(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import nvtest\n")
            fh.write("nvtest.directives.name('foo')\n")
            fh.write("nvtest.directives.name('baz')\n")
            fh.write("nvtest.directives.name('spam')\n")
            fh.write("nvtest.directives.enable(False, when=\"testname=foo\")\n")
    finder = Finder()
    finder.add(workdir)
    finder.prepare()
    tree = finder.populate()
    cases = finder.freeze(tree)
    assert len([c for c in cases if not c.masked]) == 2
