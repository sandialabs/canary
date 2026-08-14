# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

import canary
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def run_workspace(root: Path):
    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})
        session = workspace.run(specs, only="all")
        jobs = {job.name: job for job in workspace.load_jobs()}
        return workspace, session, jobs


def test_downstream_blocks_when_success_dependency_fails(tmp_path):
    root = tmp_path / "dependency-fail"
    root.mkdir()

    write(
        root / "upstream.pyt",
        """\
import canary
import sys

def test():
    raise canary.TestFailed("synthetic upstream failure")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "downstream.pyt",
        """\
import canary
import sys

canary.directives.depends_on("upstream")

def test():
    raise AssertionError("downstream should not run")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    _, session, jobs = run_workspace(root)

    assert session.returncode != 0

    assert jobs["upstream"].status.outcome.name == "FAILED"
    assert jobs["downstream"].status.outcome.name == "BLOCKED"
    assert jobs["downstream"].state.is_done()
    assert "dependency" in (jobs["downstream"].status.reason or "").lower()


def test_downstream_runs_when_dependency_is_always(tmp_path):
    root = tmp_path / "dependency-always"
    root.mkdir()

    write(
        root / "upstream.pyt",
        """\
import canary
import sys

def test():
    raise canary.TestFailed("synthetic upstream failure")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "downstream.pyt",
        """\
import canary
import sys

canary.directives.depends_on({"job": "upstream", "when": "always"})

def test():
    with open("downstream-ran.txt", "w") as fh:
        fh.write("ran")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    _, session, jobs = run_workspace(root)

    assert session.returncode != 0

    assert jobs["upstream"].status.outcome.name == "FAILED"
    assert jobs["downstream"].status.is_success()
    assert (jobs["downstream"].workspace.dir / "downstream-ran.txt").exists()


def test_downstream_runs_for_expected_diff_dependency(tmp_path):
    root = tmp_path / "dependency-diff"
    root.mkdir()

    write(
        root / "upstream.pyt",
        """\
import canary
import sys

def test():
    raise canary.TestDiffed("synthetic diff")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "downstream.pyt",
        """\
import canary
import sys

canary.directives.depends_on({"job": "upstream", "when": "DIFFED"})

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    _, session, jobs = run_workspace(root)

    # Overall session can be nonzero because upstream DIFFED is a failure category.
    assert session.returncode != 0

    assert jobs["upstream"].status.outcome.name == "DIFFED"
    assert jobs["downstream"].status.is_success()


def test_blocking_is_transitive(tmp_path):
    root = tmp_path / "dependency-transitive"
    root.mkdir()

    write(
        root / "a.pyt",
        """\
import canary
import sys

def test():
    raise canary.TestFailed("synthetic failure")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "b.pyt",
        """\
import canary
import sys

canary.directives.depends_on("a")

def test():
    raise AssertionError("b should not run")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "c.pyt",
        """\
import canary
import sys

canary.directives.depends_on("b")

def test():
    raise AssertionError("c should not run")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    _, session, jobs = run_workspace(root)

    assert session.returncode != 0

    assert jobs["a"].status.outcome.name == "FAILED"
    assert jobs["b"].status.outcome.name == "BLOCKED"
    assert jobs["c"].status.outcome.name == "BLOCKED"

    assert jobs["b"].state.is_done()
    assert jobs["c"].state.is_done()


def test_blocked_jobs_are_persisted_to_database(tmp_path):
    root = tmp_path / "dependency-block-persist"
    root.mkdir()

    write(
        root / "upstream.pyt",
        """\
import canary
import sys

def test():
    raise canary.TestFailed("synthetic upstream failure")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "downstream.pyt",
        """\
import canary
import sys

canary.directives.depends_on("upstream")

def test():
    raise AssertionError("downstream should not run")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, _, jobs = run_workspace(root)

    results = workspace.db.get_results()

    assert jobs["downstream"].id in results
    assert results[jobs["downstream"].id]["status"].outcome.name == "BLOCKED"
