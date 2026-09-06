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


def test_pyt_keywords_when_filter(tmpdir):
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


def test_pyt_exclusive_enable_skipif(tmpdir):
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


def test_pyt_sources_baseline_artifact_substitution(tmpdir):
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


def test_pyt_depends_on(tmpdir):
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


def test_pyt_modules_use_sets_modulepath(tmpdir, monkeypatch):
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


def test_pyt_xfail_xdiff(tmpdir):
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

        write(
            "test2.pyt",
            """
import canary_pyt
canary_pyt.directives.xdiff()
""",
        )
        s2 = lock_file("test2.pyt")[0]
        assert s2.xstatus != 0  # exact diff_exit_status covered elsewhere


def test_pyt_preload_rcfiles(tmpdir):
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


def test_pyt_model_default_command_uses_basename(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write("test.pyt", "import canary\n")
        s = lock_file("test.pyt")[0]
        assert s.command == [sys.executable, "test.pyt"]


INSTANCE_TEST_FILE = """
import canary
import canary_pyt


@canary_pyt.instance_test
def test_foo(inst: canary.TestInstance) -> int:
    assert inst.family == "foo"
    return 0


@canary_pyt.instance_test
def test_bar(inst):
    assert inst.family == "bar"
    return 0


@canary_pyt.instance_test
def test_baz(inst):
    return 0
"""


def test_instance_test_registers_families(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write("test.pyt", INSTANCE_TEST_FILE)
        specs = lock_file("test.pyt")
        families = sorted(s.family for s in specs)
        assert families == ["bar", "baz", "foo"]


def test_instance_test_populates_registry(tmpdir):
    from canary_pyt import instance as instance_mod

    with working_dir(tmpdir.strpath, create=True):
        write("test.pyt", INSTANCE_TEST_FILE)
        # Parsing runs the file for collection, which registers the functions.
        pyt.PYTLoader(file=pyt.PYTModel(".", "test.pyt").file).parse()
        reg = instance_mod.registered_instance_tests()
        assert sorted(reg) == ["bar", "baz", "foo"]


def test_instance_test_reset_between_files(tmpdir):
    from canary_pyt import instance as instance_mod

    with working_dir(tmpdir.strpath, create=True):
        write("a.pyt", INSTANCE_TEST_FILE)
        write(
            "b.pyt",
            "import canary\nimport canary_pyt\n"
            "@canary_pyt.instance_test\n"
            "def test_only(inst):\n    return 0\n",
        )
        pyt.PYTLoader(file=pyt.PYTModel(".", "a.pyt").file).parse()
        # Loading a second file must not raise a duplicate-registration error
        # and must not retain families from the first file.
        pyt.PYTLoader(file=pyt.PYTModel(".", "b.pyt").file).parse()
        assert sorted(instance_mod.registered_instance_tests()) == ["only"]


def test_instance_test_duplicate_raises(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "dup.pyt",
            "import canary\nimport canary_pyt\n"
            "@canary_pyt.instance_test\n"
            "def test_x(inst):\n    return 0\n"
            "@canary_pyt.instance_test\n"
            "def test_x(inst):\n    return 0\n",  # noqa: F811
        )
        try:
            pyt.PYTLoader(file=pyt.PYTModel(".", "dup.pyt").file).parse()
        except RuntimeError as e:
            assert "Duplicate instance_test" in str(e)
        else:
            raise AssertionError("expected duplicate registration to raise")


def test_run_instance_tests_dispatch(tmpdir, monkeypatch):
    """run_instance_tests() dispatches by family and returns the exit code."""
    from canary_pyt import instance as instance_mod

    instance_mod.reset_registry()

    calls = []

    class FakeInstance:
        family = "bar"

    @instance_mod.instance_test
    def test_foo(inst):
        calls.append("foo")
        return 0

    @instance_mod.instance_test
    def test_bar(inst):
        calls.append("bar")
        return 3

    import canary

    monkeypatch.setattr(canary, "get_instance", lambda arg=None: FakeInstance())
    rc = instance_mod.run_instance_tests()
    assert rc == 3
    assert calls == ["bar"]

    instance_mod.reset_registry()


def test_run_instance_tests_testfailed_exit_code(tmpdir, monkeypatch):
    from canary_pyt import instance as instance_mod

    instance_mod.reset_registry()

    class FakeInstance:
        family = "boom"

    @instance_mod.instance_test
    def test_boom(inst):
        raise canary.TestFailed("nope")

    import canary

    monkeypatch.setattr(canary, "get_instance", lambda arg=None: FakeInstance())
    rc = instance_mod.run_instance_tests()
    assert rc == canary.TestFailed.exit_code

    instance_mod.reset_registry()


def test_run_instance_tests_unknown_family(tmpdir, monkeypatch):
    from canary_pyt import instance as instance_mod

    instance_mod.reset_registry()

    class FakeInstance:
        family = "missing"

    @instance_mod.instance_test
    def test_present(inst):
        return 0

    import canary

    monkeypatch.setattr(canary, "get_instance", lambda arg=None: FakeInstance())
    try:
        instance_mod.run_instance_tests()
    except RuntimeError as e:
        assert "No @canary_pyt.instance_test registered for 'missing'" in str(e)
    else:
        raise AssertionError("expected unknown family to raise")

    instance_mod.reset_registry()
