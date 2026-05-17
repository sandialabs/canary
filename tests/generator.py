# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


import canary_pyt
from _canary.ir import DependencySpec
from _canary.util.filesystem import working_dir
from _canary.jobspec import BaselineCopyAction


def write(path: str, text: str) -> None:
    with open(path, "w") as fh:
        fh.write(text)


def test_pyt_adapter_parameterize_and_analyze(tmpdir):
    # includes the original test (updated)
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary
canary.directives.name('baz')
canary.directives.analyze()
canary.directives.owner('me')
canary.directives.keywords('test', 'unit')
canary.directives.parameterize('cpus', (1, 2, 3), when="options='baz'")
canary.directives.parameterize('a,b,c', [(1, 11, 111), (2, 22, 222), (3, 33, 333)])
""",
        )

        gen = canary_pyt.PYTAdapter(".", "test.pyt")
        specs = gen.lock(on_options=["baz"])

        assert len(specs) == 10
        assert specs[-1].attributes.get("multicase") is True
        assert "paramsets" in specs[-1].attributes


def test_pyt_adapter_keywords_when_filter(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary
canary.directives.keywords('always')
canary.directives.keywords('opt', when="options='x'")
canary.directives.keywords('p2', when={"parameters": "p=2"})
canary.directives.parameterize('p', (1, 2))
""",
        )

        gen = canary_pyt.PYTAdapter(".", "test.pyt")

        specs = gen.lock(on_options=["x"])
        # two parameter cases
        assert len(specs) == 2
        k1 = [s.keywords for s in specs if s.parameters["p"] == 1][0]
        k2 = [s.keywords for s in specs if s.parameters["p"] == 2][0]

        assert "always" in k1 and "opt" in k1 and "p2" not in k1
        assert "always" in k2 and "opt" in k2 and "p2" in k2


def test_pyt_adapter_exclusive_enable_skipif(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary
canary.directives.exclusive(when="options='x'")
canary.directives.enable(False, when="options='disable'")
canary.directives.skipif(True, reason="skip")
""",
        )

        gen = canary_pyt.PYTAdapter(".", "test.pyt")

        s1 = gen.lock(on_options=["x"])[0]
        assert s1.exclusive is True
        assert bool(s1.mask) is True  # skipif always masks currently

        s2 = gen.lock(on_options=["disable"])[0]
        assert bool(s2.mask) is True


def test_pyt_adapter_sources_baseline_artifact_substitution(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write("in_2.txt", "data\n")
        write(
            "test.pyt",
            """
import canary
canary.directives.parameterize('p', (2,))
canary.directives.copy(src='in_${P}.txt', dst='out_{p}.txt')
canary.directives.baseline(src='a_{p}.exo', dst='b_${P}.exo')
canary.directives.artifact('art_{p}.txt', upon='always')
""",
        )

        gen = canary_pyt.PYTAdapter(".", "test.pyt")
        s = gen.lock()[0]

        # copy becomes asset via file_resources; ensure substituted paths are present
        asset = s.assets[0]
        assert asset.src.name == "in_2.txt"
        assert asset.dst == "out_2.txt"

        # baseline substituted
        b = s.baseline[0]
        assert isinstance(b, BaselineCopyAction)
        assert b.src.name == "a_2.exo"
        assert b.dst == "b_2.exo"

        # artifacts substituted
        assert any(a.pattern == "art_2.txt" for a in s.artifacts)


def test_pyt_adapter_depends_on(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary
canary.directives.depends_on('foo_${x}', expect=1, result='success', when={'parameters': 'x=1'})
canary.directives.parameterize('x', (1, 2))
""",
        )

        gen = canary_pyt.PYTAdapter(".", "test.pyt")
        specs = gen.lock()

        s1 = [s for s in specs if s.parameters["x"] == 1][0]
        s2 = [s for s in specs if s.parameters["x"] == 2][0]

        assert len(s1.dependencies) == 1
        assert isinstance(s1.dependencies[0], DependencySpec)
        assert s1.dependencies[0].pattern == "foo_1"

        assert len(s2.dependencies) == 0


def test_pyt_adapter_modules_use_sets_modulepath(tmpdir, monkeypatch):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary
canary.directives.load_module('gcc', use='/m')
""",
        )
        monkeypatch.setenv("MODULEPATH", "/a:/b")

        gen = canary_pyt.PYTAdapter(".", "test.pyt")
        s = gen.lock()[0]
        assert s.environment["MODULEPATH"].startswith("/m:")
        assert "gcc" in (s.modules or [])


def test_pyt_adapter_xfail_xdiff(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary
canary.directives.xfail(code=7)
""",
        )
        s = canary_pyt.PYTAdapter(".", "test.pyt").lock()[0]
        assert s.xstatus == 7

        write(
            "test2.pyt",
            """
import canary
canary.directives.xdiff()
""",
        )
        s2 = canary_pyt.PYTAdapter(".", "test2.pyt").lock()[0]
        assert s2.xstatus != 0  # diff_exit_status (exact value covered elsewhere)


def test_pyt_adapter_preload_rcfiles(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary
canary.directives.preload('setup.sh')
canary.directives.source('rc.sh')
""",
        )

        s = canary_pyt.PYTAdapter(".", "test.pyt").lock()[0]
        assert s.preload == "setup.sh"
        assert "rc.sh" in (s.rcfiles or [])
