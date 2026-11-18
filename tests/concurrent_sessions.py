# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Several canary sessions may run in one workspace at the same time."""

import os
import subprocess
import sys
import time
from pathlib import Path

from _canary.persistence.database import WorkspaceDatabase
from _canary.persistence.listener import ResultListener


def test_results_go_to_the_central_spool(tmp_path: Path) -> None:
    db = WorkspaceDatabase.create(tmp_path)
    db.queue.put({"a": 1})
    ready = tmp_path / "var" / "spool" / "ready"
    assert [p.name for p in ready.iterdir()] != []


def test_listener_startup_leaves_live_items_alone(tmp_path: Path) -> None:
    """Another session's in-flight write and in-progress claim must survive a listener start."""
    db = WorkspaceDatabase.create(tmp_path)
    fsq = db.queue
    partial = fsq.tmp / "partial"
    partial.write_text("{")
    claimed = fsq.claimed / "00000000000000000001~host~1~0"
    claimed.write_text("{}")

    listener = ResultListener(db_root=db.root)
    listener.start()
    listener.stop_and_join()

    assert partial.exists()
    assert claimed.exists()


def test_listener_recovers_only_old_items(tmp_path: Path) -> None:
    db = WorkspaceDatabase.create(tmp_path)
    fsq = db.queue
    old = time.time() - 2 * 3600
    orphan = fsq.tmp / "orphan"
    orphan.write_text("{")
    os.utime(orphan, (old, old))
    stale = fsq.claimed / "00000000000000000001~host~1~0"
    stale.write_text("not json")
    os.utime(stale, (old, old))

    listener = ResultListener(db_root=db.root)
    listener.start()
    listener.stop_and_join()

    assert not orphan.exists()
    assert not stale.exists()
    # The stale claim was returned to ready/ and processed; unparsable -> failed/
    assert (fsq.failed / stale.name).exists()


def test_two_listeners_share_the_spool_without_loss(tmp_path: Path) -> None:
    from _canary.core.execspace import ExecutionSpace
    from _canary.core.job import Job
    from _canary.core.job import JobPhase
    from _canary.core.jobspec import JobSpec

    db = WorkspaceDatabase.create(tmp_path)
    specs = [
        JobSpec(file_root=tmp_path, file_path=Path(f"c{i}.pyt"), family=f"c{i}", id=f"{i:x}" * 64)
        for i in range(1, 9)
    ]
    db.put_specs(specs)
    listeners = [ResultListener(db_root=db.root, poll_interval=0.01) for _ in range(2)]
    for listener in listeners:
        listener.start()
    for i, spec in enumerate(specs):
        session = "a" if i % 2 else "b"
        space = ExecutionSpace(
            root=tmp_path / "sessions" / session, path=Path("x"), session=session
        )
        job = Job(spec=spec, workspace=space)
        job.timekeeper.open(at=10.0)
        for phase in ("RUNNING", "DONE"):
            job.state.phase = JobPhase(phase)
            if phase == "DONE":
                job.status.set(outcome="SUCCESS")
            db.queue.put(job)
    for listener in listeners:
        listener.stop_and_join()

    results = db.get_results()
    assert set(results) == {spec.id for spec in specs}
    assert {r["state"].phase.value for r in results.values()} == {"DONE"}
    assert not any(db.queue.ready.iterdir())
    assert not any(db.queue.claimed.iterdir())


SLOW = """\
import sys, time
import canary_pyt
canary_pyt.directives.keywords("slow")
def test():
    time.sleep(4)
if __name__ == "__main__":
    sys.exit(test())
"""

FAST = """\
import sys
import canary_pyt
canary_pyt.directives.keywords("fast")
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""


def canary(*args: str, cwd: Path) -> subprocess.Popen:
    env = {**os.environ, "CANARY_LIVE": "0"}
    env.pop("CANARY_LEVEL", None)
    return subprocess.Popen(
        [sys.executable, "-m", "canary", *args],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def test_two_sessions_run_at_once(tmp_path: Path) -> None:
    for name, text in {"slow": SLOW, "fast": FAST}.items():
        (tmp_path / name).mkdir()
        (tmp_path / name / f"{name}.pyt").write_text(text)

    first = canary("run", "slow", cwd=tmp_path)
    sessions = tmp_path / ".canary" / "sessions"
    deadline = time.time() + 60
    while not (sessions.is_dir() and any(sessions.iterdir())):
        assert first.poll() is None, first.communicate()[0]
        assert time.time() < deadline, "first session never started"
        time.sleep(0.1)

    # A second session from another directory while the first is running
    second = canary("-C", str(tmp_path / "fast"), "run", ".", cwd=tmp_path)
    out2, _ = second.communicate(timeout=120)
    assert second.returncode == 0, out2
    assert first.poll() is None, "first session finished too early to overlap"
    out1, _ = first.communicate(timeout=120)
    assert first.returncode == 0, out1

    assert len(list(sessions.iterdir())) == 2
    p = canary("status", cwd=tmp_path)
    status, _ = p.communicate(timeout=120)
    assert "2 jobs: 2 passed" in status, status
