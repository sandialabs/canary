# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import _canary.config as config
import canary
from _canary import rules
from _canary import select
from _canary import workspace
from _canary.build import Builder
from _canary.build import canary_build
from _canary.hookspec import hookimpl
from _canary.resource_pool.rpool import Outcome
from _canary.util.filesystem import mkdirp
from _canary.util.filesystem import working_dir


def select_specs(
    specs,
    *,
    keyword_exprs=None,
    parameter_expr=None,
    owners=None,
    regex=None,
    ids=None,
    prefixes=None,
):
    selector = select.Selector(specs)
    if keyword_exprs:
        selector.add_rule(rules.KeywordRule(keyword_exprs))
    if parameter_expr:
        selector.add_rule(rules.ParameterRule(parameter_expr))
    if owners:
        selector.add_rule(rules.OwnersRule(owners))
    if regex:
        selector.add_rule(rules.RegexRule(regex))
    if ids:
        selector.add_rule(rules.IDsRule(ids))
    if prefixes:
        selector.add_rule(rules.PrefixRule(prefixes))
    selector.run()
    return selector.selected


def generate_specs(generators, on_options=None):
    builder = Builder(generators=generators, on_options=on_options or [])
    specs = canary_build(builder)
    return specs


def test_skipif(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\ncanary.directives.skipif(True, reason='Because')")
        with open("b.pyt", "w") as fh:
            fh.write("import canary\ncanary.directives.skipif(False, reason='Because')")
    generators = workspace.find_generators_in_path(workdir)
    specs = generate_specs(generators)
    assert len(specs) == 2
    assert len([spec for spec in specs if not spec.mask]) == 1


def test_keywords(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\ncanary.directives.keywords('a', 'b', 'c', 'd', 'e')")
        with open("b.pyt", "w") as fh:
            fh.write("import canary\ncanary.directives.keywords('e', 'f', 'g', 'h', 'i')")
    generators = workspace.find_generators_in_path(workdir)
    specs = generate_specs(generators)
    final = select_specs(specs, keyword_exprs=["a and i"])
    assert len(final) == 0

    specs = generate_specs(generators)
    final = select_specs(specs, keyword_exprs=["a and e"])
    assert len(final) == 1

    specs = generate_specs(generators)
    final = select_specs(specs, keyword_exprs=["a or i"])
    assert len(final) == 2


def test_parameterize_1(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
    generators = workspace.find_generators_in_path(workdir)
    specs = generate_specs(generators)
    assert len([spec for spec in specs if not spec.mask]) == 3
    a, b = 0, 1
    for spec in specs:
        assert spec.parameters == {"a": a, "b": b}
        a += 2
        b += 2


def test_parameterize_2(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
            fh.write("canary.directives.parameterize('n', [10,11,12])\n")
    generators = workspace.find_generators_in_path(workdir)
    specs = generate_specs(generators)
    assert len([spec for spec in specs if not spec.mask]) == 9
    i = 0
    for a, b in [(0, 1), (2, 3), (4, 5)]:
        for n in (10, 11, 12):
            assert specs[i].parameters == {"a": a, "b": b, "n": n}
            i += 1


def test_parameterize_3(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('a,b', [(0,1),(2,3)], when='options=xxx')\n")
    generators = workspace.find_generators_in_path(workdir)
    specs = generate_specs(generators, on_options=["xxx"])
    assert len([spec for spec in specs if not spec.mask]) == 2
    specs = generate_specs(generators)
    assert len([spec for spec in specs if not spec.mask]) == 1


class Hook:
    def __init__(self, cpus):
        self.cpus = cpus

    @hookimpl
    def canary_resource_pool_accommodates(self, case):
        if case.rparameters["cpus"] > self.cpus:
            return Outcome(False, reason="Not enough cpus")
        return Outcome(True)


def test_cpu_count(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('cpus', [1, 4, 8, 32])\n")
    with canary.config.override():
        canary.config.pluginmanager.register(Hook(42), "myhook")
        generators = workspace.find_generators_in_path(workdir)
        specs = generate_specs(generators)
        assert len([spec for spec in specs if not spec.mask]) == 4
        canary.config.pluginmanager.unregister(name="myhook")
    with canary.config.override():
        canary.config.pluginmanager.register(Hook(2), "myhook")
        generators = workspace.find_generators_in_path(workdir)
        specs = generate_specs(generators)
        final = select_specs(specs)
        assert len(final) == 1
        canary.config.pluginmanager.unregister(name="myhook")


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
    generators = workspace.find_generators_in_path(workdir)
    specs = generate_specs(generators)
    assert len([spec for spec in specs if not spec.mask]) == 4
    for spec in specs:
        if spec.name == "f":
            assert len(spec.dependencies) == 1
            assert spec.dependencies[0].name == "g.n=1"


def test_analyze(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
            fh.write("canary.directives.parameterize('n', [10,11,12])\n")
            fh.write("canary.directives.generate_composite_base_case()\n")
    generators = workspace.find_generators_in_path(workdir)
    specs = generate_specs(generators)
    assert len([spec for spec in specs if not spec.mask]) == 10
    assert all(spec in specs[-1].dependencies for spec in specs[:-1])


def test_enable(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        mkdirp("a")
        with open("a/f.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("canary.directives.enable(True, when=\"options='baz and spam'\")\n")
    generators = workspace.find_generators_in_path(workdir)
    specs = generate_specs(generators, on_options=["baz"])
    assert len([spec for spec in specs if not spec.mask]) == 0
    specs = generate_specs(generators, on_options=["baz", "spam", "foo"])
    assert len([spec for spec in specs if not spec.mask]) == 1


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
    generators = workspace.find_generators_in_path(workdir)
    specs = generate_specs(generators)
    assert len([spec for spec in specs if not spec.mask]) == 2


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
canary.directives.parameterize('cpus', (1, 2), when="options='baz'")
canary.directives.parameterize('a,b,c', [(1, 11, 111), (2, 22, 222), (3, 33, 333)])
"""
            )
        with config.override():
            generators = workspace.find_generators_in_path(".")
            specs = generate_specs(generators, on_options=["baz"])
            final = select_specs(specs, keyword_exprs=["test and unit"], owners=["me"])
            assert len(specs) == 7
            assert specs[-1].attributes.get("multicase") is not None
            assert len(final) == 7

            # without the baz option, the `cpus` parameter will not be expanded so we will be left with
            # three test cases and one analyze.  The analyze will not be masked because the `cpus`
            # parameter is never expanded
            specs = generate_specs(generators)
            final = select_specs(specs, keyword_exprs=["test and unit"], owners=["me"])
            assert len(specs) == 4
            assert specs[-1].attributes.get("multicase") is not None
            assert len(final) == 4

            # with cpus<2, some of the cases will be filtered
            specs = generate_specs(generators, on_options=["baz"])
            final = select_specs(
                specs, keyword_exprs=["test and unit"], parameter_expr="cpus < 2", owners=["me"]
            )
            assert len(specs) == 7
            assert specs[-1].attributes.get("multicase") is not None
            assert len(final) == 4
            for spec in final[:-1]:
                assert spec.attributes.get("multicase") is None
                assert spec.rparameters["cpus"] != 2


def test_vvt_generator(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("test.vvt", "w") as fh:
            fh.write(
                """
# VVT: name: baz
# VVT: analyze : --analyze
# VVT: keywords: test unit
# VVT: parameterize (options=baz) : np=1 2
# VVT: parameterize : a,b,c=1,11,111 2,22,222 3,33,333
"""
            )
        with config.override():
            generators = workspace.find_generators_in_path(".")
            specs = generate_specs(generators, on_options=["baz"])
            final = select_specs(specs, keyword_exprs=["test and unit"])
            assert len(specs) == 7
            assert specs[-1].attributes.get("multicase") is not None
            assert len(final) == 7

            # without the baz option, the `np` parameter will not be expanded so we will be left with
            # three test cases and one analyze.  The analyze will not be masked because the `np`
            # parameter is never expanded
            specs = generate_specs(generators)
            final = select_specs(specs, keyword_exprs=["test and unit"])
            assert len(specs) == 4
            assert specs[-1].attributes.get("multicase") is not None
            assert len(final) == 4

            # with np<2, some of the cases will be filtered
            specs = generate_specs(generators, on_options=["baz"])
            final = select_specs(specs, keyword_exprs=["test and unit"], parameter_expr="np < 2")
            assert len(specs) == 7
            assert specs[-1].attributes.get("multicase") is not None
            assert not specs[-1].mask
            for spec in final[:-1]:
                assert spec.rparameters["cpus"] != 2


def test_many_composite(tmpdir):
    names = "abcdefghij"
    workdir = tmpdir.strpath
    with working_dir(workdir, create=True):
        for name in names:
            with open(f"{name}.pyt", "w") as fh:
                fh.write("import canary\n")
                fh.write("canary.directives.keywords('long')\n")
                fh.write(f"canary.directives.parameterize({name!r}, list(range(4)))\n")
                fh.write("canary.directives.generate_composite_base_case()\n")
    generators = workspace.find_generators_in_path(workdir)
    specs = generate_specs(generators)
    assert len(specs) == len(names) * 5
