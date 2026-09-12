# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for PYT directive parsing, model building, and spec locking.

Exercises canary_pyt.pyt internals: PYTModel, PYTLoader, PYTAdapter,
PYTLockEmitter.  These are unit tests of the pyt generator layer, not of the
higher-level collection pipeline.
"""

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


def test_parameterize_with_analyze_expands_cases(tmpdir):
    """Parameterize + analyze: N×M leaf cases plus one multi-case analyze spec."""
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.name('baz')
canary_pyt.directives.analyze()
canary_pyt.directives.owner('me')
canary_pyt.directives.keywords('test', 'unit')
canary_pyt.directives.parameterize('cpus', (1, 2, 3), when="options='baz'")
canary_pyt.directives.parameterize('a,b,c', [(1, 11, 111), (2, 22, 222), (3, 33, 333)])
""",
        )

        specs = lock_file("test.pyt", on_options=["baz"])

        # 3 cpus * 3 abc = 9 + analyze parent = 10
        assert len(specs) == 10
        assert specs[-1].attributes.get("multicase") is True
        assert "paramsets" in specs[-1].attributes


def test_keywords_when_options_filter(tmpdir):
    """keywords(when=...) conditionally adds keyword based on active options."""
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.keywords('always')
canary_pyt.directives.keywords('opt', when="options='x'")
canary_pyt.directives.keywords('p2', when={"parameters": "p=2"})
canary_pyt.directives.parameterize('p', (1, 2))
""",
        )

        specs = lock_file("test.pyt", on_options=["x"])
        assert len(specs) == 2

        k1 = [s.keywords for s in specs if s.parameters["p"] == 1][0]
        k2 = [s.keywords for s in specs if s.parameters["p"] == 2][0]

        assert "always" in k1 and "opt" in k1 and "p2" not in k1
        assert "always" in k2 and "opt" in k2 and "p2" in k2


def test_exclusive_and_skipif_mask_spec(tmpdir):
    """exclusive() and skipif(True) both produce masked specs."""
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.exclusive(when="options='x'")
canary_pyt.directives.enable(False, when="options='disable'")
canary_pyt.directives.skipif(True, reason="skip")
""",
        )

        s1 = lock_file("test.pyt", on_options=["x"])[0]
        assert s1.exclusive is True
        assert bool(s1.mask) is True  # skipif masks

        s2 = lock_file("test.pyt", on_options=["disable"])[0]
        assert bool(s2.mask) is True


def test_copy_baseline_artifact_parameter_substitution(tmpdir):
    """${P} / {p} substitution in copy/baseline/artifact paths uses parameter values."""
    with working_dir(tmpdir.strpath, create=True):
        write("in_2.txt", "data\n")
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.parameterize('p', (2,))
canary_pyt.directives.copy(src='in_${P}.txt', dst='out_{p}.txt')
canary_pyt.directives.baseline(src='a_{p}.exo', dst='b_${P}.exo')
canary_pyt.directives.artifact('art_{p}.txt', save_on='always')
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


def test_depends_on_with_when_condition(tmpdir):
    """depends_on(when=...) only adds dependency to matching parameter variants."""
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.depends_on('foo_${x}', expect=1, result='success', when={'parameters': 'x=1'})
canary_pyt.directives.parameterize('x', (1, 2))
""",
        )

        specs = lock_file("test.pyt")

        s1 = [s for s in specs if s.parameters["x"] == 1][0]
        s2 = [s for s in specs if s.parameters["x"] == 2][0]

        assert len(s1.dependencies) == 1
        assert isinstance(s1.dependencies[0], DependencySelector)
        assert s1.dependencies[0].pattern == "foo_1"

        assert len(s2.dependencies) == 0


def test_load_module_prepends_modulepath(tmpdir, monkeypatch):
    """load_module(use=...) prepends the given path to MODULEPATH."""
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.load_module('gcc', use='/m')
""",
        )
        monkeypatch.setenv("MODULEPATH", "/a:/b")

        s = lock_file("test.pyt")[0]
        assert s.environment["MODULEPATH"].startswith("/m:")
        assert "gcc" in (s.modules or [])


def test_xfail_sets_xstatus_code(tmpdir):
    """xfail(code=N) stores the expected-failure exit code on the spec."""
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.xfail(code=7)
""",
        )
        s = lock_file("test.pyt")[0]
        assert s.xstatus == 7


def test_xdiff_sets_nonzero_xstatus(tmpdir):
    """xdiff() stores a nonzero expected-diff exit code on the spec."""
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test2.pyt",
            """
import canary_pyt
canary_pyt.directives.xdiff()
""",
        )
        s2 = lock_file("test2.pyt")[0]
        assert s2.xstatus != 0


def test_preload_and_source_stored_on_spec(tmpdir):
    """preload() and source() populate the corresponding spec fields."""
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.preload('setup.sh')
canary_pyt.directives.source('rc.sh')
""",
        )

        s = lock_file("test.pyt")[0]
        assert s.preload == "setup.sh"
        assert "rc.sh" in (s.rcfiles or [])


def test_default_command_uses_python_and_basename(tmpdir):
    """A plain .pyt file with no command directive runs via the Python interpreter."""
    with working_dir(tmpdir.strpath, create=True):
        write("test.pyt", "import canary\n")
        s = lock_file("test.pyt")[0]
        assert s.command == [sys.executable, "test.pyt"]
