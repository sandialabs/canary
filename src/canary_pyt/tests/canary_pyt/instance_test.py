# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for the @canary_pyt.instance_test decorator and instance dispatch.

Covers registration, reset-between-files, duplicate detection, family
dispatch, and exit-code propagation.
"""

import os
from pathlib import Path

import _canary.job as cj
import _canary.testinst as inst
import canary
import canary_pyt.pyt as pyt
from _canary import collect
from _canary.testexec import ExecutionSpace
from _canary.util.filesystem import mkdirp
from _canary.util.filesystem import working_dir


def generate_specs(generators, on_options=None):
    from _canary.generate import Generator

    g = Generator(generators=generators, workspace=Path.cwd(), on_options=on_options or [])
    specs = g.run()
    return specs


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


def write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def test_instance_test_registers_one_family_per_decorated_function(tmpdir):
    """Each @instance_test function registers under its bare name (minus 'test_')."""
    with working_dir(tmpdir.strpath, create=True):
        write("test.pyt", INSTANCE_TEST_FILE)
        m = pyt.PYTModel(".", "test.pyt")
        pyt.PYTAdapter(m).apply(pyt.PYTLoader(file=m.file).parse())
        specs = pyt.PYTLockEmitter().lock(m)
        families = sorted(s.family for s in specs)
        assert families == ["bar", "baz", "foo"]


def test_instance_test_populates_registry(tmpdir):
    """Parsing a .pyt file populates the instance_test registry."""
    from canary_pyt import instance as instance_mod

    with working_dir(tmpdir.strpath, create=True):
        write("test.pyt", INSTANCE_TEST_FILE)
        pyt.PYTLoader(file=pyt.PYTModel(".", "test.pyt").file).parse()
        reg = instance_mod.registered_instance_tests()
        assert sorted(reg) == ["bar", "baz", "foo"]


def test_instance_test_registry_reset_between_files(tmpdir):
    """Loading a second .pyt file resets the registry; no cross-file leakage."""
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
        pyt.PYTLoader(file=pyt.PYTModel(".", "b.pyt").file).parse()
        assert sorted(instance_mod.registered_instance_tests()) == ["only"]


def test_instance_test_duplicate_registration_raises(tmpdir):
    """Registering the same family name twice raises RuntimeError."""
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


def test_run_instance_tests_dispatches_to_matching_family(tmpdir, monkeypatch):
    """run_instance_tests() calls the registered function for the active family."""
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

    monkeypatch.setattr(canary, "get_instance", lambda arg=None: FakeInstance())
    rc = instance_mod.run_instance_tests()
    assert rc == 3
    assert calls == ["bar"]

    instance_mod.reset_registry()


def test_run_instance_tests_propagates_test_failed_exit_code(tmpdir, monkeypatch):
    """TestFailed raised inside an instance_test is caught and its exit code returned."""
    from canary_pyt import instance as instance_mod

    instance_mod.reset_registry()

    class FakeInstance:
        family = "boom"

    @instance_mod.instance_test
    def test_boom(inst):
        raise canary.TestFailed("nope")

    monkeypatch.setattr(canary, "get_instance", lambda arg=None: FakeInstance())
    rc = instance_mod.run_instance_tests()
    assert rc == canary.TestFailed.exit_code

    instance_mod.reset_registry()


def test_run_instance_tests_unknown_family_raises(tmpdir, monkeypatch):
    """Dispatching to a family with no registered handler raises RuntimeError."""
    from canary_pyt import instance as instance_mod

    instance_mod.reset_registry()

    class FakeInstance:
        family = "missing"

    @instance_mod.instance_test
    def test_present(inst):
        return 0

    monkeypatch.setattr(canary, "get_instance", lambda arg=None: FakeInstance())
    try:
        instance_mod.run_instance_tests()
    except RuntimeError as e:
        assert "No @canary_pyt.instance_test registered for 'missing'" in str(e)
    else:
        raise AssertionError("expected unknown family to raise")

    instance_mod.reset_registry()


def test_multicase_instance_parameters_accessible(tmpdir):
    """A multi-case spec's TestInstance exposes all parameter combinations."""
    workdir = os.path.join(tmpdir.strpath, "src")
    with working_dir(workdir, create=True):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\n")
            fh.write("import canary_pyt\n")
            fh.write("canary_pyt.directives.analyze()\n")
            fh.write("canary_pyt.directives.parameterize('cpus', [1,2])\n")
            fh.write("canary_pyt.directives.parameterize('a,b', [(0,1),(2,3),(4,5)])\n")
    generators = collect.find_generators_in_path(workdir)
    specs = generate_specs(generators)
    assert len([spec for spec in specs if not spec.mask]) == 7
    work_tree = os.path.join(workdir, "tests")
    mkdirp(work_tree)
    with canary.config.override():
        lookup = {}
        for spec in specs:
            p = Path(work_tree)
            space = ExecutionSpace(p.parent, Path(p.name))
            deps = [cj.Dependency(job=lookup[d.spec.id], when=d.when) for d in spec.dependencies]
            job = cj.Job(spec=spec, workspace=space, dependencies=deps)
            lookup[job.id] = job
            job.save()
            instance = inst.from_job(job)
            if job.get_attribute("multicase"):
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
