# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for _canary.app.rebaseline selection helpers and keyword filtering."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

rebaseline_mod = importlib.import_module("_canary.app.rebaseline")
from _canary.app.rebaseline import filter_jobs_by_keywords
from _canary.app.rebaseline import iter_lockfiles

# ---------------------------------------------------------------------------
# iter_lockfiles
# ---------------------------------------------------------------------------


def test_iter_lockfiles_single_file(tmp_path):
    lockfile = tmp_path / "testcase.lock"
    lockfile.write_text("{}")
    result = list(iter_lockfiles(lockfile))
    assert result == [lockfile]


def test_iter_lockfiles_wrong_filename_raises(tmp_path):
    wrong = tmp_path / "wrong_name.lock"
    wrong.write_text("{}")
    with pytest.raises(ValueError, match="testcase.lock"):
        list(iter_lockfiles(wrong))


def test_iter_lockfiles_nonexistent_raises(tmp_path):
    missing = tmp_path / "nonexistent"
    with pytest.raises(ValueError, match="no such file or directory"):
        list(iter_lockfiles(missing))


def test_iter_lockfiles_empty_directory(tmp_path):
    result = list(iter_lockfiles(tmp_path))
    assert result == []


def test_iter_lockfiles_directory_with_one_lockfile(tmp_path):
    subdir = tmp_path / "job1"
    subdir.mkdir()
    lockfile = subdir / "testcase.lock"
    lockfile.write_text("{}")
    result = list(iter_lockfiles(tmp_path))
    assert len(result) == 1
    assert result[0] == lockfile


def test_iter_lockfiles_directory_with_multiple_lockfiles(tmp_path):
    for i in range(3):
        subdir = tmp_path / f"job{i}"
        subdir.mkdir()
        (subdir / "testcase.lock").write_text("{}")
    result = list(iter_lockfiles(tmp_path))
    assert len(result) == 3


def test_iter_lockfiles_nested_directories(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    lockfile = deep / "testcase.lock"
    lockfile.write_text("{}")
    result = list(iter_lockfiles(tmp_path))
    assert lockfile in result


def test_iter_lockfiles_ignores_non_lockfiles(tmp_path):
    subdir = tmp_path / "job1"
    subdir.mkdir()
    (subdir / "testcase.lock").write_text("{}")
    (subdir / "stdout.txt").write_text("output")
    result = list(iter_lockfiles(tmp_path))
    assert len(result) == 1


# ---------------------------------------------------------------------------
# filter_jobs_by_keywords
# ---------------------------------------------------------------------------


class _FakeSpec:
    def __init__(self, keywords=None):
        self.keywords = keywords or []
        self.implicit_keywords = []


class _FakeJob:
    def __init__(self, keywords=None):
        self.spec = _FakeSpec(keywords)


def test_filter_jobs_by_keywords_none_returns_all():
    jobs = [_FakeJob(["fast"]), _FakeJob(["slow"])]
    result = filter_jobs_by_keywords(jobs, None)
    assert result == jobs


def test_filter_jobs_by_keywords_empty_list_returns_all():
    jobs = [_FakeJob(["fast"]), _FakeJob(["slow"])]
    result = filter_jobs_by_keywords(jobs, [])
    assert result == jobs


def test_filter_jobs_by_keywords_matching():
    fast = _FakeJob(["fast", "unit"])
    slow = _FakeJob(["slow", "integration"])
    result = filter_jobs_by_keywords([fast, slow], ["fast"])
    assert fast in result
    assert slow not in result


def test_filter_jobs_by_keywords_no_match_returns_empty():
    jobs = [_FakeJob(["fast"]), _FakeJob(["slow"])]
    result = filter_jobs_by_keywords(jobs, ["nonexistent"])
    assert result == []


def test_filter_jobs_by_keywords_all_match():
    jobs = [_FakeJob(["fast"]), _FakeJob(["fast", "smoke"])]
    result = filter_jobs_by_keywords(jobs, ["fast"])
    assert len(result) == 2


def test_filter_jobs_by_keywords_negation():
    fast = _FakeJob(["fast"])
    slow = _FakeJob(["slow"])
    result = filter_jobs_by_keywords([fast, slow], ["not slow"])
    # "not slow" should include only jobs without "slow"
    assert fast in result
    assert slow not in result


# ---------------------------------------------------------------------------
# DB-first rebaseline selection
# ---------------------------------------------------------------------------


class _DBSpec:
    def __init__(self, spec_id: str, *, keywords=None):
        self.id = spec_id
        self.name = spec_id
        self.keywords = keywords or []
        self.implicit_keywords = []
        self.mask = None
        self.rparameters = {}
        self.environment = {}
        self.attributes = {}
        self.owners = []
        self.timeout = -1.0
        self.baseline = []
        self.assets = []
        self.xstatus = 0
        self.preload = None
        self.rcfiles = []
        self.artifacts = []
        self.exclusive = False
        self.command = []
        self.exec_path = None
        self.file_root = Path(".")
        self.file_path = Path(f"{spec_id}.pyt")
        self.dependencies = []

    @property
    def file(self):
        return self.file_root / self.file_path

    def display_name(self, **kwargs):
        return self.id


class _DBJob:
    def __init__(self, spec_id: str, *, keywords=None, workspace=None):
        self.id = spec_id
        self.spec = _DBSpec(spec_id, keywords=keywords)
        self.workspace = workspace

    def display_name(self, **kwargs):
        return self.id


class _FakeDB:
    def __init__(self):
        self._resolved = {"job-a": "id-a", "job-b": "id-b"}
        self._view_selected = ["id-a"]
        self._partial_specs = []
        self._results = {
            "id-a": {
                "id": "id-a",
                "session": "latest",
                "workspace": "suite/case",
                "status": object(),
                "timekeeper": object(),
                "measurements": {},
                "state": object(),
            },
            "id-b": {
                "id": "id-b",
                "session": "latest",
                "workspace": "other/case",
                "status": object(),
                "timekeeper": object(),
                "measurements": {},
                "state": object(),
            },
        }
        self._session_rows = {
            "s1": [
                {
                    "id": "id-a",
                    "session": "s1",
                    "workspace": "suite/case",
                    "status": object(),
                    "timekeeper": object(),
                    "measurements": {},
                    "state": object(),
                },
                {
                    "id": "id-b",
                    "session": "s1",
                    "workspace": "other/case",
                    "status": object(),
                    "timekeeper": object(),
                    "measurements": {},
                    "state": object(),
                },
            ]
        }

    def resolve_spec_id(self, value: str):
        return self._resolved.get(value)

    def select_from_view(self, prefixes: list[str]) -> list[str]:
        self.last_prefixes = prefixes
        return list(self._view_selected)

    def get_partial_specs(self, *, tag=None):
        return list(self._partial_specs)

    def load_specs(self, ids=None, include_upstreams=False):
        specs = {
            "id-a": _DBSpec("id-a", keywords=["fast"]),
            "id-b": _DBSpec("id-b", keywords=["slow"]),
        }
        return [specs[i] for i in ids or []]

    def get_results(self, ids=None, include_upstreams=False):
        if ids is None:
            return dict(self._results)
        return {i: self._results[i] for i in ids}

    def get_results_for_session(self, session):
        return list(self._session_rows.get(session, []))


class _FakeWorkspace:
    def __init__(self, root: Path):
        self.root = root
        self.sessions_dir = root / ".canary" / "sessions"
        self.db = _FakeDB()
        self._relative_to_view = None
        self._loaded_jobs: list[str] | None = None
        self._jobs = {
            "id-a": _DBJob("id-a", keywords=["fast"]),
            "id-b": _DBJob("id-b", keywords=["slow"]),
        }

    def relative_to_view(self, path):
        return self._relative_to_view

    def is_session_dir(self, path):
        return Path(path).absolute().is_relative_to(self.sessions_dir)

    def load_jobs(self, ids=None):
        self._loaded_jobs = list(ids or [])
        return [self._jobs[i] for i in ids or []]

    def find(self, *, job=None, spec=None):
        assert spec is None
        return self._jobs[self.db.resolve_spec_id(job)]


def test_resolve_rebaseline_jobs_uses_view_prefixes_without_walk(monkeypatch, tmp_path):
    workspace = _FakeWorkspace(tmp_path)
    target = tmp_path / "TestResults" / "suite"
    target.mkdir(parents=True)
    workspace._relative_to_view = "suite"

    def fail_walk(*args, **kwargs):
        raise AssertionError("os.walk should not be called for view-path selection")

    monkeypatch.setattr(rebaseline_mod.os, "walk", fail_walk)

    jobs = rebaseline_mod.resolve_rebaseline_jobs(workspace, str(target))

    assert workspace.db.last_prefixes == ["suite/%"]
    assert [job.id for job in jobs] == ["id-a"]
    assert workspace._loaded_jobs == ["id-a"]


def test_resolve_rebaseline_jobs_uses_explicit_job_id_without_walk(monkeypatch, tmp_path):
    workspace = _FakeWorkspace(tmp_path)

    def fail_walk(*args, **kwargs):
        raise AssertionError("os.walk should not be called for id selection")

    monkeypatch.setattr(rebaseline_mod.os, "walk", fail_walk)

    jobs = rebaseline_mod.resolve_rebaseline_jobs(workspace, "job-a")

    assert [job.id for job in jobs] == ["id-a"]
    assert workspace._loaded_jobs is None


def test_rebaseline_applies_keyword_filter_before_loading_jobs(monkeypatch, tmp_path):
    workspace = _FakeWorkspace(tmp_path)
    target = tmp_path / "TestResults" / "suite"
    target.mkdir(parents=True)
    workspace._relative_to_view = "suite"
    workspace.db._view_selected = ["id-a", "id-b"]

    monkeypatch.setattr(rebaseline_mod, "open_workspace", lambda: workspace)
    monkeypatch.setattr(
        rebaseline_mod.config,
        "pluginmanager",
        SimpleNamespace(hook=SimpleNamespace(canary_runtest_rebaseline=lambda case: None)),
    )

    count = rebaseline_mod.rebaseline(str(target), keyword_exprs=["fast"])

    assert count == 1
    assert workspace._loaded_jobs == ["id-a"]


def test_resolve_rebaseline_jobs_from_session_path_uses_matching_session_row(tmp_path):
    workspace = _FakeWorkspace(tmp_path)
    session_dir = workspace.sessions_dir / "s1" / "suite" / "case"
    session_dir.mkdir(parents=True)

    jobs = rebaseline_mod.resolve_rebaseline_jobs(workspace, str(session_dir))

    assert workspace._loaded_jobs is None
    assert [job.id for job in jobs] == ["id-a"]
    assert jobs[0].workspace.session == "s1"
    assert jobs[0].workspace.dir == session_dir


def test_resolve_rebaseline_jobs_from_workspace_root_uses_latest_results_without_walk(
    monkeypatch, tmp_path
):
    workspace = _FakeWorkspace(tmp_path)
    workspace.root.mkdir(parents=True, exist_ok=True)

    def fail_walk(*args, **kwargs):
        raise AssertionError("os.walk should not be called for workspace-root selection")

    monkeypatch.setattr(rebaseline_mod.os, "walk", fail_walk)

    jobs = rebaseline_mod.resolve_rebaseline_jobs(workspace, str(workspace.root))

    assert sorted(job.id for job in jobs) == ["id-a", "id-b"]
    assert workspace._loaded_jobs == ["id-a", "id-b"]


# ---------------------------------------------------------------------------
# Multiple targets
# ---------------------------------------------------------------------------


def _patch_rebaseline_app(monkeypatch, workspace):
    """Route app.rebaseline at *workspace* and record hook calls instead of running them."""
    calls: list[str] = []
    hook = SimpleNamespace(canary_runtest_rebaseline=lambda case: calls.append(case.id))
    monkeypatch.setattr(rebaseline_mod, "open_workspace", lambda: workspace)
    monkeypatch.setattr(
        rebaseline_mod, "config", SimpleNamespace(pluginmanager=SimpleNamespace(hook=hook))
    )
    return calls


def test_resolve_rebaseline_targets_unions_job_ids_in_order(tmp_path):
    workspace = _FakeWorkspace(tmp_path)

    jobs = rebaseline_mod.resolve_rebaseline_targets(workspace, ["job-b", "job-a"])

    assert [job.id for job in jobs] == ["id-b", "id-a"]


def test_resolve_rebaseline_targets_deduplicates_same_job(tmp_path):
    workspace = _FakeWorkspace(tmp_path)
    workspace.db._resolved["id-a"] = "id-a"  # the full id resolves, as does the name

    jobs = rebaseline_mod.resolve_rebaseline_targets(workspace, ["job-a", "id-a", "job-a"])

    assert [job.id for job in jobs] == ["id-a"]


def test_resolve_rebaseline_targets_keeps_same_job_from_distinct_result_dirs(tmp_path):
    """Explicitly selecting one job's results from two sessions keeps both selections."""
    workspace = _FakeWorkspace(tmp_path)
    s1, s2 = SimpleNamespace(dir=tmp_path / "s1" / "case"), SimpleNamespace(dir=tmp_path / "s2")
    by_target = {"one": [_DBJob("id-a", workspace=s1)], "two": [_DBJob("id-a", workspace=s2)]}

    def fake_resolve(ws, target, keyword_exprs=None):
        return by_target[target]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(rebaseline_mod, "resolve_rebaseline_jobs", fake_resolve)
        jobs = rebaseline_mod.resolve_rebaseline_targets(workspace, ["one", "two", "one"])

    assert [job.workspace for job in jobs] == [s1, s2]


def test_resolve_rebaseline_targets_applies_keywords_to_every_target(tmp_path):
    workspace = _FakeWorkspace(tmp_path)

    jobs = rebaseline_mod.resolve_rebaseline_targets(
        workspace, ["job-a", "job-b"], keyword_exprs=["slow"]
    )

    assert [job.id for job in jobs] == ["id-b"]


def test_rebaseline_accepts_multiple_targets(monkeypatch, tmp_path):
    workspace = _FakeWorkspace(tmp_path)
    calls = _patch_rebaseline_app(monkeypatch, workspace)

    n = rebaseline_mod.rebaseline(["job-a", "job-b"])

    assert n == 2
    assert calls == ["id-a", "id-b"]


def test_rebaseline_single_string_target_still_supported(monkeypatch, tmp_path):
    workspace = _FakeWorkspace(tmp_path)
    calls = _patch_rebaseline_app(monkeypatch, workspace)

    assert rebaseline_mod.rebaseline("job-b") == 1
    assert calls == ["id-b"]


def test_rebaseline_unknown_target_aborts_before_any_rebaseline(monkeypatch, tmp_path):
    workspace = _FakeWorkspace(tmp_path)
    calls = _patch_rebaseline_app(monkeypatch, workspace)

    def find(*, job=None, spec=None):
        if (spec_id := workspace.db.resolve_spec_id(job)) is None:
            raise ValueError(f"{job}: no matching test job found")
        return workspace._jobs[spec_id]

    monkeypatch.setattr(workspace, "find", find)

    with pytest.raises(ValueError, match="nope"):
        rebaseline_mod.rebaseline(["job-a", "nope", "job-b"])
    assert calls == []


def test_rebaseline_empty_target_list_selects_nothing(monkeypatch, tmp_path):
    workspace = _FakeWorkspace(tmp_path)
    calls = _patch_rebaseline_app(monkeypatch, workspace)

    def fail(*args, **kwargs):
        raise AssertionError("an empty target list must not resolve anything")

    monkeypatch.setattr(rebaseline_mod, "resolve_rebaseline_jobs", fail)

    assert rebaseline_mod.rebaseline([]) == 0
    assert calls == []


def test_rebaseline_cli_accepts_multiple_targets_and_defaults_to_cwd(monkeypatch):
    from _canary.cli import rebaseline as cli_rebaseline

    seen: list = []
    # Patch the ``app`` object the CLI module actually holds.  A dotted-string
    # target ("_canary.app.rebaseline") is resolved via the ``_canary.app``
    # package attribute, which earlier tests can leave pointing at a stale copy
    # of the module that differs from sys.modules["_canary.app"].
    monkeypatch.setattr(
        cli_rebaseline.app, "rebaseline", lambda targets, keyword_exprs=None: seen.append(targets)
    )
    cmd = cli_rebaseline.Rebaseline()
    cmd.execute(SimpleNamespace(targets=["a", "b"], keyword_exprs=None))
    cmd.execute(SimpleNamespace(targets=[], keyword_exprs=None))

    assert seen == [["a", "b"], ["."]]
