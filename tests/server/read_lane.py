# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The read lane: reads run beside the work lane, in a bounded pool, with a time limit."""

import time

import pytest

from _canary.service.fs import server
from _canary.service.fs.testing import Serving
from _canary.service.fs.testing import cancel
from _canary.service.fs.testing import drop
from _canary.service.fs.testing import run
from _canary.service.fs.testing import status
from _canary.service.fs.testing import wait_for
from _canary.service.fs.testing import wait_result

#: A query that never ends on its own (only an interrupt stops it).
ENDLESS = {
    "path": "/canary/query/db",
    "request": {
        "sql": "SELECT count(*) FROM (WITH RECURSIVE r(i) AS "
        "(SELECT 1 UNION ALL SELECT i + 1 FROM r) SELECT i FROM r)"
    },
}


@pytest.fixture
def lane(monkeypatch):
    """Set the read lane's size and time limit, then start a server."""
    servers = []

    def start(root, *, workers=4, timeout=300):
        monkeypatch.setattr(server, "READ_WORKERS", workers)
        monkeypatch.setattr(server, "READ_TIMEOUT", timeout)
        servers.append(Serving(root).start())
        return servers[-1]

    yield start
    for s in servers:
        s.stop()


def test_a_status_answers_while_a_run_is_in_progress(root, lane):
    lane(root)
    drop(root, "long", run(["slow"]))
    wait_for(lambda: status(root, "long").get("state") == "running")
    started = time.time()
    drop(root, "status", {"path": "/canary/status"})
    assert wait_result(root, "status", timeout=10)["state"] == "done"
    assert time.time() - started < 10
    assert status(root, "long")["state"] == "running"
    cancel(root, "long")
    assert wait_result(root, "long")["state"] == "cancelled"


def test_a_slow_read_does_not_hold_up_other_reads(root, lane):
    lane(root, workers=2)
    drop(root, "slow", ENDLESS)
    wait_for(lambda: status(root, "slow").get("state") == "running")
    drop(root, "quick", {"path": "/canary/query/sessions"})
    assert wait_result(root, "quick", timeout=10)["state"] == "done"
    cancel(root, "slow")
    assert wait_result(root, "slow", timeout=10)["state"] == "cancelled"


def test_reads_beyond_the_pool_wait_their_turn(root, lane):
    lane(root, workers=2)
    for name in ("r1", "r2", "r3"):
        drop(root, name, ENDLESS)
        time.sleep(0.02)
    wait_for(lambda: [status(root, n).get("state") for n in ("r1", "r2")] == ["running"] * 2)
    time.sleep(0.5)
    assert status(root, "r3")["state"] == "queued"
    cancel(root, "r1")
    wait_for(lambda: status(root, "r3").get("state") == "running", 10)  # took r1's thread
    cancel(root, "r2"), cancel(root, "r3")
    results = [wait_result(root, n, timeout=10) for n in ("r1", "r2", "r3")]
    assert [r["state"] for r in results] == ["cancelled"] * 3


def test_a_read_past_its_time_limit_fails_and_frees_its_thread(root, lane):
    lane(root, workers=1, timeout=1)
    drop(root, "endless", ENDLESS)
    result = wait_result(root, "endless", timeout=15)
    assert (result["state"], result["status_code"]) == ("failed", 500)
    assert "time limit" in result["error"] and result["finished"] - result["started"] < 5
    drop(root, "after", {"path": "/canary/query/sessions"})  # the one thread is free again
    assert wait_result(root, "after", timeout=10)["state"] == "done"


def test_a_running_read_can_be_cancelled(root, lane):
    lane(root, workers=1)
    drop(root, "endless", ENDLESS)
    wait_for(lambda: status(root, "endless").get("state") == "running")
    cancel(root, "endless")
    result = wait_result(root, "endless", timeout=10)
    assert (result["state"], result["status_code"]) == ("cancelled", 499)
    drop(root, "after", {"path": "/canary/query/sessions"})
    assert wait_result(root, "after", timeout=10)["state"] == "done"


def test_stopping_the_server_fails_reads_in_progress(root, lane):
    serving = lane(root, workers=1)
    drop(root, "endless", ENDLESS)
    wait_for(lambda: status(root, "endless").get("state") == "running")
    serving.stop()
    result = wait_result(root, "endless", timeout=1)
    assert (result["state"], result["error"]) == ("failed", "server stopped")
