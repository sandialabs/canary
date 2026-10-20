# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""No test process may outlive canary, however the session ends.

Each scenario starts ``canary run`` on a test that spawns long-lived
grandchildren (tests run in their own session, so terminal signals never reach
them directly), ends the session abnormally, and asserts that no process
carrying the test's unique marker survives.
"""

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psutil
import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups required"),
]


def _write_test(root: Path, marker: str, extra: str = "") -> None:
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "t.pyt").write_text(
        f"""import subprocess, sys, time
import canary
{extra}
if __name__ == "__main__":
    py = sys.executable
    subprocess.Popen([py, "-c", "import time; time.sleep(300)", "{marker}"])
    subprocess.Popen(["sh", "-c", py + " -c 'import time; time.sleep(300)' {marker} & wait"])
    time.sleep(300)
"""
    )


def _marked(marker: str) -> list[psutil.Process]:
    found = []
    me = os.getpid()
    for p in psutil.process_iter(["cmdline"]):
        try:
            if p.pid != me and any(marker in a for a in (p.info["cmdline"] or [])):
                found.append(p)
        except psutil.Error:
            pass
    return found


def _reap(marker: str) -> None:
    for p in _marked(marker):
        try:
            p.kill()
        except psutil.Error:
            pass


def _wait_until(pred, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.2)
    return pred()


def _run_scenario(tmp_path: Path, action: str, extra_args=(), extra="") -> tuple[int, Path]:
    marker = f"canarymark{uuid.uuid4().hex}"
    _write_test(tmp_path, marker, extra)
    env = dict(os.environ, CANARY_LIVE="0", CANARY_KILL_GRACE="1", CANARY_DISABLE_KB="1")
    out = open(tmp_path / "out.txt", "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "canary", "run", *extra_args, "tests"],
        cwd=tmp_path,
        env=env,
        stdout=out,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        assert _wait_until(lambda: len(_marked(marker)) >= 2, 90), (
            "test never started:\n" + (tmp_path / "out.txt").read_text()[-2000:]
        )
        if action == "SIGINT":
            os.killpg(proc.pid, signal.SIGINT)  # like Ctrl-C on the terminal
        elif action in ("SIGTERM", "SIGKILL"):
            os.kill(proc.pid, getattr(signal, action))
        elif action == "kill-file":
            session = sorted((tmp_path / ".canary" / "sessions").iterdir())[-1]
            (session / "canary.kill").touch()
        rc = proc.wait(timeout=90)
        assert _wait_until(lambda: not _marked(marker), 10), (
            f"{len(_marked(marker))} test process(es) survived canary ({action})"
        )
        return rc, tmp_path
    finally:
        if proc.poll() is None:
            proc.kill()
        _reap(marker)
        out.close()


def _job_status(root: Path) -> dict:
    locks = list((root / ".canary" / "sessions").glob("*/**/testcase.lock"))
    assert locks, "no testcase.lock written"
    return json.loads(locks[0].read_text())


def test_sigint_reaps_test_processes(tmp_path):
    rc, root = _run_scenario(tmp_path, "SIGINT")
    assert rc == signal.SIGINT.value
    assert _job_status(root)["status"]["category"] == "ABORTED"


def test_sigterm_reaps_test_processes(tmp_path):
    rc, root = _run_scenario(tmp_path, "SIGTERM")
    assert rc == 128 + signal.SIGTERM.value
    data = _job_status(root)
    assert data["state"]["phase"] == "DONE"
    assert data["status"]["category"] == "ABORTED"


def test_sigkill_of_canary_reaps_test_processes(tmp_path):
    if not sys.platform.startswith("linux"):
        pytest.skip("relies on PR_SET_PDEATHSIG")
    rc, _ = _run_scenario(tmp_path, "SIGKILL")
    assert rc == -signal.SIGKILL.value


def test_kill_file_reaps_test_processes(tmp_path):
    _run_scenario(tmp_path, "kill-file")


def test_session_timeout_reaps_test_processes(tmp_path):
    # ``a`` (3 s) then ``b`` (marked, long-running); each fits the 6 s session
    # budget on its own so neither is filtered out, but the session expires
    # while ``b`` is still running -- well before b's own 5 s timeout.
    marker = f"canarymark{uuid.uuid4().hex}"
    (tmp_path / "tests").mkdir(parents=True)
    (tmp_path / "tests" / "a.pyt").write_text(
        "import time, canary\ncanary.directives.timeout(5)\n"
        "if __name__ == '__main__':\n    time.sleep(3)\n"
    )
    (tmp_path / "tests" / "b.pyt").write_text(
        f"""import subprocess, sys, time, canary
canary.directives.timeout(5)
canary.directives.depends_on("a")
if __name__ == "__main__":
    subprocess.Popen(["sh", "-c", sys.executable + " -c 'import time; time.sleep(300)' {marker} & wait"])
    time.sleep(300)
"""
    )
    env = dict(os.environ, CANARY_LIVE="0", CANARY_KILL_GRACE="1", CANARY_DISABLE_KB="1")
    try:
        start = time.time()
        cp = subprocess.run(
            [sys.executable, "-m", "canary", "run", "--timeout", "session=6s", "tests"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert cp.returncode != 0
        assert "Session timed out" in cp.stdout + cp.stderr
        assert time.time() - start < 30
        assert _wait_until(lambda: not _marked(marker), 10), "test process survived session timeout"
    finally:
        _reap(marker)


def test_test_timeout_reaps_grandchildren(tmp_path):
    rc, root = _run_scenario(tmp_path, "none", extra="canary.directives.timeout(2)")
    assert _job_status(root)["status"]["outcome"] in ("TIMEOUT", 68)
