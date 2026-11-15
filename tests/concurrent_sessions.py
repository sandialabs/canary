# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Several canary sessions may run in one workspace at the same time."""

import os
import subprocess
import sys
import time
from pathlib import Path

from _canary.persistence.database import SPOOL_DIRNAME
from _canary.persistence.database import ResultListener
from _canary.persistence.database import ResultSpool
from _canary.persistence.database import WorkspaceDatabase


def test_results_are_spooled_per_session(tmp_path: Path) -> None:
    spool = ResultSpool(tmp_path)
    spool.put({"a": 1})  # no session: legacy workspace spool
    assert (tmp_path / "tmp/db/ready").is_dir()
    q_a = spool.for_session("a")
    q_b = spool.for_session("b")
    assert q_a.root == tmp_path / "sessions" / "a" / SPOOL_DIRNAME
    assert q_b.root == tmp_path / "sessions" / "b" / SPOOL_DIRNAME
    assert spool.for_session("a") is q_a


def test_listener_startup_leaves_other_sessions_alone(tmp_path: Path) -> None:
    db = WorkspaceDatabase.create(tmp_path)
    other = db.queue.for_session("other")
    # A record that session "other" is in the middle of writing
    partial = other.tmp / "partial"
    partial.write_text("{")
    listener = ResultListener(db, sessions=["mine"])
    listener.start()
    listener.stop_and_join()
    assert partial.exists()


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
