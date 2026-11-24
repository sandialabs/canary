# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The workspace in-use lock: removal refuses while a canary command or server uses it."""

import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

import canary
from _canary import app
from _canary.workspace import inuse
from _canary.workspace.workspace import Workspace

PASSING = (
    'import sys\ndef test():\n    return 0\nif __name__ == "__main__":\n    sys.exit(test())\n'
)


def _holder(root):
    """A separate process holding the shared lock until killed; returns once it holds it."""
    code = textwrap.dedent(
        f"""
        import sys, time
        from _canary.workspace import inuse
        with inuse.using({str(root)!r}):
            print("holding", flush=True)
            time.sleep(600)
        """
    )
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert proc.stdout is not None and proc.stdout.readline().strip() == "holding"
    return proc


def test_removal_refuses_while_another_process_uses_the_workspace(tmp_path):
    root = Workspace.create(tmp_path).root
    holder = _holder(root)
    try:
        with pytest.raises(inuse.WorkspaceInUseError, match="stop it first"):
            Workspace.detach(tmp_path)
        assert root.exists()
    finally:
        holder.kill()
        holder.wait()
    assert Workspace.detach(tmp_path) is not None
    assert not root.exists()


def test_a_killed_holder_leaves_no_stale_lock(tmp_path):
    root = Workspace.create(tmp_path).root
    holder = _holder(root)
    holder.send_signal(signal.SIGKILL)  # no finally, no atexit
    holder.wait()
    assert Workspace.detach(tmp_path) is not None


def test_many_may_use_a_workspace_at_once(tmp_path):
    root = Workspace.create(tmp_path).root
    holders = [_holder(root) for _ in range(3)]
    try:
        with inuse.using(root):  # a fourth, in this process
            with pytest.raises(inuse.WorkspaceInUseError):
                Workspace.remove(tmp_path)
    finally:
        for holder in holders:
            holder.kill()
            holder.wait()
    assert Workspace.remove(tmp_path) is not None


def test_run_w_refuses_while_the_workspace_is_in_use(tmp_path, monkeypatch):
    """Through app.run, not only the command line (the old CLI hook missed this)."""
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "ok.pyt").write_text(PASSING)
    root = Workspace.create(tmp_path).root
    monkeypatch.chdir(tmp_path)
    holder = _holder(root)
    try:
        with canary.config.override(), pytest.raises(inuse.WorkspaceInUseError):
            request = app.pathspec.ScanPathsRequest(value={str(tmp_path / "ok"): []})
            app.run(request, app.RunOptions(wipe_workspace=True, work_tree=str(tmp_path)))
        assert root.exists()
    finally:
        holder.kill()
        holder.wait()


def test_a_running_canary_run_holds_the_workspace(tmp_path):
    (tmp_path / "slow").mkdir()
    (tmp_path / "slow" / "slow.pyt").write_text(
        'import sys, time\nif __name__ == "__main__":\n    time.sleep(30)\n    sys.exit(0)\n'
    )

    def canary_(*args):
        return subprocess.run(
            [sys.executable, "-m", "canary", *args], cwd=tmp_path, capture_output=True, text=True
        )

    assert canary_("init", ".").returncode == 0
    run = subprocess.Popen(
        [sys.executable, "-m", "canary", "run", "slow"],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.time() + 60
        while not list((tmp_path / ".canary").glob("sessions/*/slow")):
            assert time.time() < deadline and run.poll() is None, "the run never started"
            time.sleep(0.1)
        refused = canary_("rm")
        assert refused.returncode != 0 and "stop it first" in refused.stderr, refused.stderr
        assert (tmp_path / ".canary").exists()
    finally:
        os.killpg(run.pid, signal.SIGKILL)
        run.wait()
    assert canary_("rm").returncode == 0
