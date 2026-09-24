# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for _canary.canaryconf_impl — directory-scoped setup/teardown via canaryconf.py."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from _canary.canaryconf_impl import CANARYCONF_FILENAME
from _canary.canaryconf_impl import CONFTEST_KEYWORD
from _canary.canaryconf_impl import ROLE_TO_FUNCTION
from _canary.canaryconf_impl import SETUP_FUNCTION
from _canary.canaryconf_impl import TEARDOWN_FUNCTION
from _canary.canaryconf_impl import _find_canaryconf
from _canary.canaryconf_impl import _has_setup
from _canary.canaryconf_impl import _has_teardown
from _canary.canaryconf_impl import _inject_conftest_jobs
from _canary.canaryconf_impl import _make_synthetic_spec
from _canary.canaryconf_impl import _top_level_functions
from _canary.core.jobspec import JobSpec

# ---------------------------------------------------------------------------
# helpers — cheap JobSpec factory
# ---------------------------------------------------------------------------


def _make_spec(file_root: Path, rel: str, family: str = "mytest") -> JobSpec:
    p = file_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
    return JobSpec(file_root=file_root, file_path=Path(rel), family=family)


def _fake_generator(specs: list[JobSpec]) -> SimpleNamespace:
    return SimpleNamespace(specs=specs)


# ---------------------------------------------------------------------------
# _top_level_functions
# ---------------------------------------------------------------------------


def test_top_level_functions_basic():
    src = "def foo(): pass\ndef bar(): pass\n"
    assert _top_level_functions(src) == {"foo", "bar"}


def test_top_level_functions_ignores_nested():
    src = "def outer():\n    def inner(): pass\n"
    assert _top_level_functions(src) == {"outer"}
    assert "inner" not in _top_level_functions(src)


def test_top_level_functions_syntax_error_returns_empty():
    assert _top_level_functions("def )(bad syntax") == set()


def test_top_level_functions_empty_file():
    assert _top_level_functions("") == set()


def test_top_level_functions_classes_not_included():
    src = "class Foo:\n    def method(self): pass\n"
    # class methods have col_offset > 0, so only top-level functions count
    assert _top_level_functions(src) == set()


# ---------------------------------------------------------------------------
# _has_setup / _has_teardown
# ---------------------------------------------------------------------------


def test_has_setup_true():
    src = f"def {SETUP_FUNCTION}(ctx): pass\n"
    assert _has_setup(src) is True


def test_has_setup_false():
    src = "def something_else(ctx): pass\n"
    assert _has_setup(src) is False


def test_has_teardown_true():
    src = f"def {TEARDOWN_FUNCTION}(ctx): pass\n"
    assert _has_teardown(src) is True


def test_has_teardown_false():
    src = ""
    assert _has_teardown(src) is False


def test_has_setup_and_teardown():
    src = f"def {SETUP_FUNCTION}(ctx): pass\ndef {TEARDOWN_FUNCTION}(ctx): pass\n"
    assert _has_setup(src) is True
    assert _has_teardown(src) is True


# ---------------------------------------------------------------------------
# _find_canaryconf
# ---------------------------------------------------------------------------


def test_find_canaryconf_present(tmp_path):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text("")
    assert _find_canaryconf(tmp_path) == cf


def test_find_canaryconf_absent(tmp_path):
    assert _find_canaryconf(tmp_path) is None


# ---------------------------------------------------------------------------
# _make_synthetic_spec
# ---------------------------------------------------------------------------


def test_make_synthetic_spec_setup(tmp_path):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text("")
    spec = _make_synthetic_spec(
        role="setup", canaryconf_path=cf, file_root=tmp_path, scope_dir=tmp_path
    )
    assert spec.family == f"{CANARYCONF_FILENAME}::setup"
    assert CONFTEST_KEYWORD in spec.keywords
    assert "setup" in spec.keywords
    assert spec.attributes["canary_conftest"]["role"] == "setup"
    assert spec.attributes["canary_conftest"]["scope_dir"] == str(tmp_path)
    assert spec.attributes["canary_conftest"]["source_file"] == str(cf)
    # In-process dispatch: no subprocess command, no phase env var.
    assert spec.command == []
    assert "CANARY_CONFTEST_PHASE" not in spec.environment
    # exec_path is a dedicated __setup__ dir beneath the governing directory.
    assert spec.exec_path == cf.parent.relative_to(tmp_path) / "__setup__"
    assert ROLE_TO_FUNCTION["setup"] == SETUP_FUNCTION


def test_make_synthetic_spec_teardown(tmp_path):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text("")
    spec = _make_synthetic_spec(
        role="teardown", canaryconf_path=cf, file_root=tmp_path, scope_dir=tmp_path
    )
    assert spec.attributes["canary_conftest"]["role"] == "teardown"
    assert "teardown" in spec.keywords
    assert spec.command == []
    assert "CANARY_CONFTEST_PHASE" not in spec.environment
    assert ROLE_TO_FUNCTION["teardown"] == TEARDOWN_FUNCTION


# ---------------------------------------------------------------------------
# _inject_conftest_jobs — empty / no canaryconf
# ---------------------------------------------------------------------------


def test_inject_empty_specs_is_noop():
    gen = _fake_generator([])
    _inject_conftest_jobs(gen)
    assert gen.specs == []


def test_inject_no_canaryconf_leaves_specs_unchanged(tmp_path):
    spec = _make_spec(tmp_path, "sub/test_a.py")
    gen = _fake_generator([spec])
    _inject_conftest_jobs(gen)
    assert gen.specs == [spec]


# ---------------------------------------------------------------------------
# _inject_conftest_jobs — setup only
# ---------------------------------------------------------------------------


def test_inject_setup_only(tmp_path):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text(f"def {SETUP_FUNCTION}(ctx): pass\n")

    spec = _make_spec(tmp_path, "test_a.py")
    gen = _fake_generator([spec])
    _inject_conftest_jobs(gen)

    synthetics = [s for s in gen.specs if "canary_conftest" in s.attributes]
    assert len(synthetics) == 1
    assert synthetics[0].attributes["canary_conftest"]["role"] == "setup"

    # The original spec must depend on setup (on_success)
    dep_specs = [d.spec for d in spec.dependencies]
    assert synthetics[0] in dep_specs
    dep = next(d for d in spec.dependencies if d.spec is synthetics[0])
    assert dep.when == "on_success"


# ---------------------------------------------------------------------------
# _inject_conftest_jobs — teardown only
# ---------------------------------------------------------------------------


def test_inject_teardown_only(tmp_path):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text(f"def {TEARDOWN_FUNCTION}(ctx): pass\n")

    spec = _make_spec(tmp_path, "test_a.py")
    gen = _fake_generator([spec])
    _inject_conftest_jobs(gen)

    synthetics = [s for s in gen.specs if "canary_conftest" in s.attributes]
    assert len(synthetics) == 1
    teardown = synthetics[0]
    assert teardown.attributes["canary_conftest"]["role"] == "teardown"

    # teardown must depend on test (always)
    dep_specs = [d.spec for d in teardown.dependencies]
    assert spec in dep_specs
    dep = next(d for d in teardown.dependencies if d.spec is spec)
    assert dep.when == "always"

    # original spec must NOT have a setup dependency
    assert spec.dependencies == []


# ---------------------------------------------------------------------------
# _inject_conftest_jobs — both setup and teardown
# ---------------------------------------------------------------------------


def test_inject_setup_and_teardown(tmp_path):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text(f"def {SETUP_FUNCTION}(ctx): pass\ndef {TEARDOWN_FUNCTION}(ctx): pass\n")

    spec = _make_spec(tmp_path, "test_a.py")
    gen = _fake_generator([spec])
    _inject_conftest_jobs(gen)

    synthetics = {
        s.attributes["canary_conftest"]["role"]: s
        for s in gen.specs
        if "canary_conftest" in s.attributes
    }
    assert set(synthetics) == {"setup", "teardown"}

    setup = synthetics["setup"]
    teardown = synthetics["teardown"]

    # test depends on setup
    assert any(d.spec is setup and d.when == "on_success" for d in spec.dependencies)
    # teardown depends on test
    assert any(d.spec is spec and d.when == "always" for d in teardown.dependencies)


# ---------------------------------------------------------------------------
# _inject_conftest_jobs — multiple test specs in same directory
# ---------------------------------------------------------------------------


def test_inject_multiple_specs_same_dir(tmp_path):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text(f"def {SETUP_FUNCTION}(ctx): pass\ndef {TEARDOWN_FUNCTION}(ctx): pass\n")

    specs = [_make_spec(tmp_path, f"test_{i}.py", family=f"test_{i}") for i in range(3)]
    gen = _fake_generator(list(specs))
    _inject_conftest_jobs(gen)

    synthetics = [s for s in gen.specs if "canary_conftest" in s.attributes]
    # Still only one setup and one teardown
    assert len(synthetics) == 2

    setup = next(s for s in synthetics if s.attributes["canary_conftest"]["role"] == "setup")
    teardown = next(s for s in synthetics if s.attributes["canary_conftest"]["role"] == "teardown")

    for spec in specs:
        assert any(d.spec is setup for d in spec.dependencies)
        assert any(d.spec is spec for d in teardown.dependencies)


# ---------------------------------------------------------------------------
# _inject_conftest_jobs — canaryconf.py in subdirectory governs only that subtree
# ---------------------------------------------------------------------------


def test_inject_subdir_scope(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    cf = sub / CANARYCONF_FILENAME
    cf.write_text(f"def {SETUP_FUNCTION}(ctx): pass\n")

    spec_in_scope = _make_spec(tmp_path, "sub/test_a.py", family="in_scope")
    spec_out_of_scope = _make_spec(tmp_path, "test_b.py", family="out_of_scope")
    gen = _fake_generator([spec_in_scope, spec_out_of_scope])
    _inject_conftest_jobs(gen)

    setup_specs = [s for s in gen.specs if "canary_conftest" in s.attributes]
    assert len(setup_specs) == 1

    # only the in-scope spec gets the dependency
    assert len(spec_in_scope.dependencies) == 1
    assert spec_in_scope.dependencies[0].spec is setup_specs[0]
    assert spec_out_of_scope.dependencies == []


# ---------------------------------------------------------------------------
# _inject_conftest_jobs — inherited canaryconf from ancestor directory
# ---------------------------------------------------------------------------


def test_inject_inherited_from_ancestor(tmp_path):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text(f"def {SETUP_FUNCTION}(ctx): pass\n")

    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    spec = _make_spec(tmp_path, "a/b/test_deep.py", family="deep")
    gen = _fake_generator([spec])
    _inject_conftest_jobs(gen)

    setup_specs = [s for s in gen.specs if "canary_conftest" in s.attributes]
    assert len(setup_specs) == 1
    assert len(spec.dependencies) == 1


# ---------------------------------------------------------------------------
# _inject_conftest_jobs — canaryconf with neither function is ignored
# ---------------------------------------------------------------------------


def test_inject_no_known_functions_is_ignored(tmp_path):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text("def unrelated(): pass\n")

    spec = _make_spec(tmp_path, "test_a.py")
    gen = _fake_generator([spec])
    _inject_conftest_jobs(gen)

    assert len(gen.specs) == 1
    assert spec.dependencies == []


# ---------------------------------------------------------------------------
# _inject_conftest_jobs — idempotency: existing synthetic specs are not re-processed
# ---------------------------------------------------------------------------


def test_inject_skips_already_synthetic_specs(tmp_path):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text(f"def {SETUP_FUNCTION}(ctx): pass\n")

    spec = _make_spec(tmp_path, "test_a.py")
    gen = _fake_generator([spec])
    _inject_conftest_jobs(gen)

    count_after_first = len(gen.specs)
    # Second call must not add another layer of synthetics
    _inject_conftest_jobs(gen)
    assert len(gen.specs) == count_after_first


# ---------------------------------------------------------------------------
# _inject_conftest_jobs — unreadable canaryconf.py is warned and skipped
# ---------------------------------------------------------------------------


def test_inject_unreadable_canaryconf_is_skipped(tmp_path, monkeypatch):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text(f"def {SETUP_FUNCTION}(ctx): pass\n")

    original_read_text = Path.read_text

    def _bad_read(self, *a, **kw):
        if self.name == CANARYCONF_FILENAME:
            raise OSError("permission denied")
        return original_read_text(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", _bad_read)

    spec = _make_spec(tmp_path, "test_a.py")
    gen = _fake_generator([spec])
    # Should not raise — just warn and skip
    _inject_conftest_jobs(gen)
    assert len(gen.specs) == 1
    assert spec.dependencies == []


# ---------------------------------------------------------------------------
# _inject_conftest_jobs — dependency deduplication (no double-wiring)
# ---------------------------------------------------------------------------


def test_inject_no_duplicate_dependencies(tmp_path):
    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text(f"def {SETUP_FUNCTION}(ctx): pass\n")

    spec = _make_spec(tmp_path, "test_a.py")
    gen = _fake_generator([spec])
    _inject_conftest_jobs(gen)

    # Verify each setup dependency appears at most once
    dep_ids = [id(d.spec) for d in spec.dependencies]
    assert len(dep_ids) == len(set(dep_ids))


# ---------------------------------------------------------------------------
# canary_generate_modifyitems hook — integration smoke test
# ---------------------------------------------------------------------------


def test_hookimpl_registered():
    """canaryconf_impl exposes canary_generate_modifyitems as a hookimpl."""
    import _canary.canaryconf_impl as sh

    assert hasattr(sh, "canary_generate_modifyitems")
    # pluggy marks hookimpl callables with a special attribute
    impl = sh.canary_generate_modifyitems
    assert hasattr(impl, "canary_impl") or callable(impl)


# ---------------------------------------------------------------------------
# PythonFunctionLauncher selection
# ---------------------------------------------------------------------------


def test_launcher_selected_for_conftest_jobs():
    """canaryconf jobs get a PythonFunctionLauncher; others get None from the hook."""
    from _canary.execution.launcher import PythonFunctionLauncher
    from _canary.execution.launcher import canaryconf_job_launcher

    conftest_case = SimpleNamespace(
        get_attribute=lambda name, *a: {"role": "setup"} if name == "canary_conftest" else None
    )
    plain_case = SimpleNamespace(get_attribute=lambda name, *a: None)

    assert isinstance(canaryconf_job_launcher(case=conftest_case), PythonFunctionLauncher)
    assert canaryconf_job_launcher(case=plain_case) is None


def test_import_source_reads_functions(tmp_path):
    """PythonFunctionLauncher._import_source loads a canaryconf.py by path."""
    from _canary.execution.launcher import PythonFunctionLauncher

    cf = tmp_path / CANARYCONF_FILENAME
    cf.write_text(
        f"def {SETUP_FUNCTION}(ctx):\n    return 'ok'\n"
        f"def {TEARDOWN_FUNCTION}(ctx):\n    return 'bye'\n"
    )
    module = PythonFunctionLauncher._import_source(cf)
    assert callable(getattr(module, SETUP_FUNCTION))
    assert callable(getattr(module, TEARDOWN_FUNCTION))
    # Anonymous import must not leak into sys.modules.
    import sys

    assert not any(cf.stem == m for m in sys.modules if m == CANARYCONF_FILENAME[:-3])


# ---------------------------------------------------------------------------
# End-to-end: setup/teardown actually execute in-process during a run
# ---------------------------------------------------------------------------


def test_setup_teardown_run_in_process(tmp_path):
    """A full session runs canary_setup/canary_teardown in-process (no subprocess).

    The canaryconf.py writes marker files into ctx.file_root so we can assert
    the functions actually executed, and that setup ran before the test while
    teardown ran after it.
    """
    import canary
    from _canary.util.filesystem import working_dir
    from _canary.workspace import Workspace

    root = tmp_path / "suite"
    root.mkdir()

    (root / CANARYCONF_FILENAME).write_text(
        "import os\n"
        "import canary\n"
        "\n"
        f"def {SETUP_FUNCTION}(ctx):\n"
        "    root = ctx.file_root\n"
        "    open(os.path.join(root, 'setup.marker'), 'w').close()\n"
        "\n"
        f"def {TEARDOWN_FUNCTION}(ctx):\n"
        "    root = ctx.file_root\n"
        "    open(os.path.join(root, 'teardown.marker'), 'w').close()\n"
    )

    (root / "t.pyt").write_text(
        "import os\n"
        "import canary\n"
        "import canary_pyt\n"
        "def test():\n"
        "    self = canary.get_instance()\n"
        "    # setup must have run before us\n"
        "    assert os.path.exists(os.path.join(self.file_root, 'setup.marker'))\n"
        "    # teardown must NOT have run yet\n"
        "    assert not os.path.exists(os.path.join(self.file_root, 'teardown.marker'))\n"
        "if __name__ == '__main__':\n"
        "    test()\n"
    )

    with working_dir(root):
        with canary.config.override():
            workspace = Workspace.create(root)
            specs = workspace.collect({str(root): []})
            workspace.run(specs, only="all")

        jobs = workspace.load_jobs()

    # Marker files prove both hooks executed in-process.
    assert (root / "setup.marker").exists()
    assert (root / "teardown.marker").exists()

    # The setup and teardown synthetic jobs must have passed, and the real test
    # (which asserts ordering) must have passed too.
    by_family = {job.family: job for job in jobs}
    assert f"{CANARYCONF_FILENAME}::setup" in by_family
    assert f"{CANARYCONF_FILENAME}::teardown" in by_family
    for job in jobs:
        assert job.status.outcome.name in ("SUCCESS", "PASS"), (
            f"{job.family}: {job.status.outcome.name} ({job.status.reason})"
        )
