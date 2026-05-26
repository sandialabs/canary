# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary_pyt.pyt as pyt
from _canary.ir import DependencySelector
from _canary.jobspec import BaselineCopyAction
from _canary.util.filesystem import working_dir


def write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def make_model_and_apply(path: str = "test.pyt") -> pyt.PYTModel:
    m = pyt.PYTModel(".", path)
    calls = pyt.PYTLoader(file=m.file).parse()
    pyt.PYTAdapter(m).apply(calls)
    return m


def lock_file(path: str, *, on_options=None):
    m = make_model_and_apply(path)
    return pyt.PYTLockEmitter().lock(m, on_options=on_options or [])


def test_pyt_parameterize_and_analyze(tmpdir):
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

        specs = lock_file("test.pyt", on_options=["baz"])

        # 3 cpus * 3 abc = 9 + analyze parent = 10
        assert len(specs) == 10
        assert specs[-1].attributes.get("multicase") is True
        assert "paramsets" in specs[-1].attributes


def test_pyt_keywords_when_filter(tmpdir):
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

        specs = lock_file("test.pyt", on_options=["x"])
        assert len(specs) == 2

        k1 = [s.keywords for s in specs if s.parameters["p"] == 1][0]
        k2 = [s.keywords for s in specs if s.parameters["p"] == 2][0]

        assert "always" in k1 and "opt" in k1 and "p2" not in k1
        assert "always" in k2 and "opt" in k2 and "p2" in k2


def test_pyt_exclusive_enable_skipif(tmpdir):
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

        s1 = lock_file("test.pyt", on_options=["x"])[0]
        assert s1.exclusive is True
        assert bool(s1.mask) is True  # skipif masks

        s2 = lock_file("test.pyt", on_options=["disable"])[0]
        assert bool(s2.mask) is True


def test_pyt_sources_baseline_artifact_substitution(tmpdir):
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

        s = lock_file("test.pyt")[0]

        asset = s.assets[0]
        assert asset.src.name == "in_2.txt"
        assert asset.dst == "out_2.txt"

        b = s.baseline[0]
        assert isinstance(b, BaselineCopyAction)
        assert b.src.name == "a_2.exo"
        assert b.dst == "b_2.exo"

        assert any(a.pattern == "art_2.txt" for a in s.artifacts)


def test_pyt_depends_on(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary
canary.directives.depends_on('foo_${x}', expect=1, result='success', when={'parameters': 'x=1'})
canary.directives.parameterize('x', (1, 2))
""",
        )

        specs = lock_file("test.pyt")

        s1 = [s for s in specs if s.parameters["x"] == 1][0]
        s2 = [s for s in specs if s.parameters["x"] == 2][0]

        assert len(s1.dependencies) == 1
        assert isinstance(s1.dependencies[0], DependencySelector)
        assert s1.dependencies[0].pattern == "foo_1"

        assert len(s2.dependencies) == 0


def test_pyt_modules_use_sets_modulepath(tmpdir, monkeypatch):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary
canary.directives.load_module('gcc', use='/m')
""",
        )
        monkeypatch.setenv("MODULEPATH", "/a:/b")

        s = lock_file("test.pyt")[0]
        assert s.environment["MODULEPATH"].startswith("/m:")
        assert "gcc" in (s.modules or [])


def test_pyt_xfail_xdiff(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary
canary.directives.xfail(code=7)
""",
        )
        s = lock_file("test.pyt")[0]
        assert s.xstatus == 7

        write(
            "test2.pyt",
            """
import canary
canary.directives.xdiff()
""",
        )
        s2 = lock_file("test2.pyt")[0]
        assert s2.xstatus != 0  # exact diff_exit_status covered elsewhere


def test_pyt_preload_rcfiles(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary
canary.directives.preload('setup.sh')
canary.directives.source('rc.sh')
""",
        )

        s = lock_file("test.pyt")[0]
        assert s.preload == "setup.sh"
        assert "rc.sh" in (s.rcfiles or [])


def test_pyt_model_default_command_uses_basename(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write("test.pyt", "import canary\n")
        s = lock_file("test.pyt")[0]
        assert s.command == [sys.executable, "test.pyt"]
