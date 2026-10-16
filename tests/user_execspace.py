# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for the built-in ``--exec-prefix`` plugin (``_canary.plugins.user_execspace``)."""

import json
import os
from pathlib import Path

import pytest

from _canary.plugins import user_execspace as ues
from _canary.session.workspace import Workspace
from _canary.util import json_helper
from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand

PASS_BODY = """\
import os
import sys
import canary
canary.directives.parameterize("x", (1, 2))

def test():
    canary.get_instance()
    with open("out.txt", "w") as fh:
        fh.write(os.getcwd())
    os.symlink(os.path.abspath("out.txt"), "abs_link")
    os.symlink("out.txt", "rel_link")
    return 0

if __name__ == "__main__":
    sys.exit(test())
"""

FAIL_BODY = """\
import sys

def test():
    with open("fail.dat", "w") as fh:
        fh.write("y")
    return 1

if __name__ == "__main__":
    sys.exit(test())
"""

TIMEOUT_BODY = """\
import sys
import time
import canary
canary.directives.timeout(1)

def test():
    with open("partial.dat", "w") as fh:
        fh.write("x")
    time.sleep(30)

if __name__ == "__main__":
    sys.exit(test())
"""


def _load_job(job_dir: Path):
    return json_helper.safeload(str(job_dir / "testcase.lock"))


def _session_dir(src: Path) -> Path:
    sessions = sorted((src / ".canary/sessions").iterdir())
    assert sessions
    return sessions[-1]


def _run(src: Path, *args: str, env: dict[str, str] | None = None):
    kwargs = {"env": env} if env is not None else {}
    with working_dir(str(src)):
        return CanaryCommand("run")(*args, ".", **kwargs)


# ---------------------------------------------------------------------------
# unit tests
# ---------------------------------------------------------------------------


def test_resolve_prefix_expands_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_PREFIX_ROOT", str(tmp_path))
    assert ues.resolve_prefix("$MY_PREFIX_ROOT/fast") == tmp_path / "fast"


def test_resolve_prefix_rejects_unexpanded_env():
    with pytest.raises(ValueError, match="unresolved environment variable"):
        ues.resolve_prefix("$CANARY_SURELY_UNDEFINED_VAR_123/x")


def test_session_exec_root_is_unique_per_workspace(tmp_path):
    a = ues.session_exec_root(tmp_path, Path("/ws/a/.canary"), "S")
    b = ues.session_exec_root(tmp_path, Path("/ws/b/.canary"), "S")
    assert a != b
    assert a.parent.parent == tmp_path / "canary"
    assert a.name == "S"
    # Deterministic, so concurrent runs of a session (e.g. HPC batches) share it.
    assert a == ues.session_exec_root(tmp_path, Path("/ws/a/.canary"), "S")


def test_copy_back_preserves_links_and_writes_lock_last(tmp_path):
    exec_root = tmp_path / "pfx" / "S"
    src = exec_root / "job"
    src.mkdir(parents=True)
    (src / "out.txt").write_text("data")
    (src / "sub").mkdir()
    (src / "sub" / "deep.txt").write_text("deep")
    (src / "testcase.lock").write_text("{}")
    (src / "rel").symlink_to("out.txt")
    (src / "abs").symlink_to(src / "out.txt")
    external = tmp_path / "external.txt"
    external.write_text("ext")
    (src / "ext").symlink_to(external)

    host_session = tmp_path / "host" / "S"
    dst = host_session / "job"
    dst.mkdir(parents=True)
    (dst / "stale.txt").write_text("old")

    assert ues.copy_back(src, dst, exec_root=exec_root)
    assert (dst / "out.txt").read_text() == "data"
    assert (dst / "sub" / "deep.txt").read_text() == "deep"
    assert (dst / "testcase.lock").read_text() == "{}"
    assert not (dst / "stale.txt").exists()
    assert os.readlink(dst / "rel") == "out.txt"
    assert Path(os.readlink(dst / "abs")) == dst / "out.txt"
    assert Path(os.readlink(dst / "ext")) == external
    assert not list(dst.glob(".testcase.lock.*"))


def test_copy_back_missing_source_is_noop(tmp_path):
    assert ues.copy_back(tmp_path / "nope", tmp_path / "dst", exec_root=tmp_path) is False
    assert not (tmp_path / "dst").exists()


def test_replace_dir_variables():
    class J:
        variables = {"PATH": "/old/dir:/usr/bin", "PYTHONPATH": "/old/dir", "OTHER": "/old/dir:/x"}

    ues._replace_dir_variables(J, old=Path("/old/dir"), new=Path("/new/dir"))  # type: ignore[arg-type]
    assert J.variables["PATH"] == "/new/dir:/usr/bin"
    assert J.variables["PYTHONPATH"] == "/new/dir"
    assert J.variables["OTHER"] == "/old/dir:/x"


# ---------------------------------------------------------------------------
# end-to-end
# ---------------------------------------------------------------------------


def test_exec_prefix_runs_below_prefix_and_copies_back(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    prefix = tmp_path / "fast"
    (src / "a.pyt").write_text(PASS_BODY)

    cp = _run(src, "-w", f"--exec-prefix={prefix}")
    assert cp.returncode == 0, cp.stdout

    session = _session_dir(src)
    for name in ("a.x=1", "a.x=2"):
        job_dir = session / name
        # The job ran below the prefix ...
        ran_in = Path((job_dir / "out.txt").read_text())
        assert str(ran_in).startswith(str(prefix / "canary"))
        assert ran_in.name == name
        # ... and its outputs are back in the session directory.
        assert (job_dir / "canary-out.txt").exists()
        assert os.readlink(job_dir / "rel_link") == "out.txt"
        assert Path(os.readlink(job_dir / "abs_link")) == job_dir / "out.txt"
        lock = json.loads((job_dir / "testcase.lock").read_text())
        assert str(prefix) not in json.dumps(lock["workspace"])
        assert str(prefix) not in json.dumps(lock.get("variables", {}))

    # The execution tree is left in place below the prefix.
    exec_root = ues.session_exec_root(prefix, src / ".canary", session.name)
    for name in ("a.x=1", "a.x=2"):
        assert (exec_root / name / "out.txt").exists()

    # Results view points at the session directory.
    view = src / "TestResults"
    for name in ("a.x=1", "a.x=2"):
        assert Path(os.readlink(view / name)) == session / name

    # Runtime history was recorded in the workspace cache.
    assert list((src / ".canary/cache/jobs").rglob("*.jsonl"))

    # The parent's database reflects the results, with host-relative paths.
    with working_dir(str(src)):
        ws = Workspace.load()
        jobs = ws.load_jobs()
    assert {j.name for j in jobs} == {"a.x=1", "a.x=2"}
    for job in jobs:
        assert job.status.outcome.name == "SUCCESS"
        assert job.workspace.dir == session / job.name
        assert _load_job(session / job.name).workspace.dir == session / job.name


def test_exec_prefix_failures_and_timeouts_are_copied(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    prefix = tmp_path / "fast"
    (src / "c.pyt").write_text(FAIL_BODY)
    (src / "t.pyt").write_text(TIMEOUT_BODY)

    cp = _run(src, "-w", f"--exec-prefix={prefix}")
    assert cp.returncode != 0

    session = _session_dir(src)
    assert (session / "c" / "fail.dat").read_text() == "y"
    assert (session / "t" / "partial.dat").read_text() == "x"
    assert _load_job(session / "c").status.outcome.name == "FAILED"
    assert _load_job(session / "t").status.outcome.name == "TIMEOUT"
    assert (prefix / "canary").is_dir()


def test_exec_prefix_env_default(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.pyt").write_text(PASS_BODY)
    env = dict(os.environ)
    env["FAST_ROOT"] = str(tmp_path)
    # Default comes from CANARY_EXEC_PREFIX; env vars are expanded at run time.
    env[ues.EXEC_PREFIX_ENV] = "$FAST_ROOT/fast"

    cp = _run(src, "-w", env=env)
    assert cp.returncode == 0, cp.stdout

    job_dir = _session_dir(src) / "a.x=1"
    assert Path((job_dir / "out.txt").read_text()).is_relative_to(tmp_path / "fast" / "canary")


def test_exec_prefix_not_set_runs_in_session(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.pyt").write_text(PASS_BODY)
    cp = _run(src, "-w")
    assert cp.returncode == 0, cp.stdout
    session = _session_dir(src)
    assert Path((session / "a.x=1" / "out.txt").read_text()) == session / "a.x=1"
