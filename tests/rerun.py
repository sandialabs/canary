# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import time
from pathlib import Path

import pytest

import canary
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def create_workspace(root: Path) -> tuple[Workspace, list[canary.JobSpec]]:
    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})
        return workspace, specs


def run_specs(workspace: Workspace, specs: list[canary.JobSpec], *, only: str = "all"):
    with working_dir(workspace.root), canary.config.override():
        return workspace.run(specs, only=only)


def jobs_by_name(workspace: Workspace) -> dict[str, canary.Job]:
    return {job.name: job for job in workspace.load_jobs()}


def test_rerun_not_pass_reruns_failed_but_not_success(tmp_path):
    root = tmp_path / "rerun-not-pass"
    root.mkdir()

    control = root / "fail.txt"
    control.write_text("fail")

    write(
        root / "pass_case.pyt",
        """\
import sys

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "maybe_fail.pyt",
        f"""\
import pathlib
import sys
import canary

def test():
    if pathlib.Path({str(control)!r}).read_text().strip() == "fail":
        raise canary.TestFailed("first run failure")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, specs = create_workspace(root)

    session1 = run_specs(workspace, specs, only="all")
    jobs1 = jobs_by_name(workspace)

    assert session1.returncode != 0
    assert jobs1["pass_case"].status.is_success()
    assert jobs1["maybe_fail"].status.outcome.name == "FAILED"

    pass_started_1 = jobs1["pass_case"].timekeeper.started
    fail_started_1 = jobs1["maybe_fail"].timekeeper.started

    # Fix the failing test.
    time.sleep(0.01)
    control.write_text("pass")

    session2 = run_specs(workspace, specs, only="not_pass")
    jobs2 = jobs_by_name(workspace)

    assert session2.returncode == 0
    assert jobs2["pass_case"].status.is_success()
    assert jobs2["maybe_fail"].status.is_success()

    # The passing job should not have rerun; the failed job should have.
    assert jobs2["pass_case"].timekeeper.started == pass_started_1
    assert jobs2["maybe_fail"].timekeeper.started > fail_started_1


def test_rerun_all_reruns_successful_jobs(tmp_path):
    root = tmp_path / "rerun-all"
    root.mkdir()

    write(
        root / "case.pyt",
        """\
import sys

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, specs = create_workspace(root)

    session1 = run_specs(workspace, specs, only="all")
    jobs1 = jobs_by_name(workspace)
    started_1 = jobs1["case"].timekeeper.started

    time.sleep(0.01)

    session2 = run_specs(workspace, specs, only="all")
    jobs2 = jobs_by_name(workspace)

    assert session1.returncode == 0
    assert session2.returncode == 0
    assert jobs2["case"].timekeeper.started > started_1


def test_rerun_failed_includes_blocked_downstream_after_upstream_fixed(tmp_path):
    root = tmp_path / "rerun-blocked"
    root.mkdir()

    control = root / "fail.txt"
    control.write_text("fail")

    write(
        root / "upstream.pyt",
        f"""\
import pathlib
import sys
import canary

def test():
    if pathlib.Path({str(control)!r}).read_text().strip() == "fail":
        raise canary.TestFailed("upstream failed")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "downstream.pyt",
        """\
import sys
import canary

canary.directives.depends_on("upstream")

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, specs = create_workspace(root)

    session1 = run_specs(workspace, specs, only="all")
    jobs1 = jobs_by_name(workspace)

    assert session1.returncode != 0
    assert jobs1["upstream"].status.outcome.name == "FAILED"
    assert jobs1["downstream"].status.outcome.name == "BLOCKED"

    # Fix upstream. Rerun failed should include the failed upstream and
    # blocked downstream through rerun/dependency closure.
    time.sleep(0.01)
    control.write_text("pass")

    session2 = run_specs(workspace, specs, only="failed")
    jobs2 = jobs_by_name(workspace)

    assert session2.returncode == 0
    assert jobs2["upstream"].status.is_success()
    assert jobs2["downstream"].status.is_success()


def test_rerun_not_run_runs_only_jobs_without_results(tmp_path):
    root = tmp_path / "rerun-not-run"
    root.mkdir()

    write(
        root / "a.pyt",
        """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "b.pyt",
        """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, specs = create_workspace(root)

    # Run only one spec first.
    spec_a = [spec for spec in specs if spec.family == "a"][0]
    session1 = run_specs(workspace, [spec_a], only="all")
    jobs1 = jobs_by_name(workspace)

    assert session1.returncode == 0
    assert "a" in jobs1

    # Now run full suite with not_run. Only b should run.
    session2 = run_specs(workspace, specs, only="not_run")
    jobs2 = jobs_by_name(workspace)

    assert session2.returncode == 0
    assert jobs2["a"].timekeeper.started == jobs1["a"].timekeeper.started
    assert jobs2["b"].status.is_success()


def test_rerun_changed_runs_modified_spec_only(tmp_path):
    root = tmp_path / "rerun-changed"
    root.mkdir()

    a = root / "a.pyt"
    b = root / "b.pyt"

    write(
        a,
        """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        b,
        """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, specs = create_workspace(root)

    session1 = run_specs(workspace, specs, only="all")
    jobs1 = jobs_by_name(workspace)

    assert session1.returncode == 0
    a_started_1 = jobs1["a"].timekeeper.started
    b_started_1 = jobs1["b"].timekeeper.started

    time.sleep(0.05)
    a.write_text(
        """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
# modified
"""
    )

    session2 = run_specs(workspace, specs, only="changed")
    jobs2 = jobs_by_name(workspace)

    assert session2.returncode == 0
    assert jobs2["a"].timekeeper.started > a_started_1
    assert jobs2["b"].timekeeper.started == b_started_1


def test_rerun_changed_runs_modified_spec_not_downstream_for_direct_workspace_run(tmp_path):
    root = tmp_path / "rerun-changed-downstream"
    root.mkdir()

    upstream = root / "upstream.pyt"

    write(
        upstream,
        """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "downstream.pyt",
        """\
import sys
import canary

canary.directives.depends_on("upstream")

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, specs = create_workspace(root)

    session1 = run_specs(workspace, specs, only="all")
    jobs1 = jobs_by_name(workspace)

    assert session1.returncode == 0
    upstream_started_1 = jobs1["upstream"].timekeeper.started
    downstream_started_1 = jobs1["downstream"].timekeeper.started

    time.sleep(0.05)
    upstream.write_text(
        """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
# modified
"""
    )

    session2 = run_specs(workspace, specs, only="changed")
    jobs2 = jobs_by_name(workspace)

    assert session2.returncode == 0
    assert jobs2["upstream"].timekeeper.started > upstream_started_1

    # Direct Workspace.run(..., only="changed") applies RuntimeSelector rules
    # to the supplied jobs and does not compute downstream closure. The CLI
    # rerun path is responsible for dependency-closure expansion.
    assert jobs2["downstream"].timekeeper.started == downstream_started_1


@pytest.mark.skipif(True, reason="Rerun closure still being worked on")
def test_rerun_changed_includes_downstream_closure(tmp_path):
    root = tmp_path / "rerun-changed-downstream"
    root.mkdir()

    upstream = root / "upstream.pyt"

    write(
        upstream,
        """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "downstream.pyt",
        """\
import sys
import canary

canary.directives.depends_on("upstream")

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, specs = create_workspace(root)

    session1 = run_specs(workspace, specs, only="all")
    jobs1 = jobs_by_name(workspace)

    assert session1.returncode == 0
    upstream_started_1 = jobs1["upstream"].timekeeper.started
    downstream_started_1 = jobs1["downstream"].timekeeper.started

    time.sleep(0.05)
    upstream.write_text(
        """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
# modified
"""
    )

    session2 = run_specs(workspace, specs, only="changed")
    jobs2 = jobs_by_name(workspace)

    assert session2.returncode == 0
    assert jobs2["upstream"].timekeeper.started > upstream_started_1
    assert jobs2["downstream"].timekeeper.started > downstream_started_1
