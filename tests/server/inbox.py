# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The file binding, end to end: a caller uses only inbox/, requests/<id>/ and server.json."""

import getpass
import json
import os
import socket
import threading
import time

import pytest

from _canary import config
from _canary.service.fs import server
from _canary.service.fs.testing import Serving
from _canary.service.fs.testing import cancel
from _canary.service.fs.testing import drop
from _canary.service.fs.testing import read_json
from _canary.service.fs.testing import request_dir
from _canary.service.fs.testing import run
from _canary.service.fs.testing import server_dir
from _canary.service.fs.testing import status
from _canary.service.fs.testing import wait_for
from _canary.service.fs.testing import wait_result

# ---------------------------------------------------------------- results


def test_a_run_ends_done_with_its_exit_code(root, serving):
    drop(root, "good", run(["ok"]))
    time.sleep(0.02)  # distinct mtimes: the inbox is taken oldest first
    drop(root, "bad", run(["failing"]))
    good, bad = wait_result(root, "good"), wait_result(root, "bad")
    assert (good["state"], good["status_code"], good["data"]) == ("done", 200, {"exit_code": 0})
    assert bad["state"] == "done" and bad["data"]["exit_code"] != 0
    assert good["path"] == "/canary/run" and good["user"] == getpass.getuser()
    assert good["submitted"] <= good["started"] <= good["finished"] <= bad["started"]
    assert "1 pass" in (request_dir(root, "good") / "stdout").read_text()
    assert not list((server_dir(root) / "inbox").iterdir())


def test_a_read_answers_through_the_same_files(root, serving):
    drop(root, "s", {"path": "/canary/status"})
    result = wait_result(root, "s")
    assert (result["state"], result["data"]) == ("done", [])


def test_a_tmp_file_is_ignored_until_it_is_renamed(root, serving):
    inbox = server_dir(root) / "inbox"
    tmp = inbox / "later.json.tmp"
    tmp.write_text(json.dumps({"path": "/canary/status"}))
    time.sleep(1.0)
    assert tmp.exists() and not request_dir(root, "later").exists()
    os.rename(tmp, inbox / "later.json")
    assert wait_result(root, "later")["state"] == "done"


def test_the_user_is_the_files_owner_and_cannot_be_supplied(root, serving):
    drop(root, "mine", {"path": "/canary/status"})
    assert wait_result(root, "mine")["user"] == getpass.getuser()
    drop(root, "forged", {"path": "/canary/status", "user": "mallory"})
    forged = wait_result(root, "forged")
    assert (forged["status_code"], forged["state"]) == (400, "rejected")


def test_result_json_is_written_after_all_output(root, serving, monkeypatch):
    original = server._copy

    def slow_copy(pipe, path):  # the copy lags the child by a second
        def later():
            time.sleep(1.0)
            original(pipe, path).join()

        thread = threading.Thread(target=later, daemon=True)
        thread.start()
        return thread

    monkeypatch.setattr(server, "_copy", slow_copy)
    drop(root, "out", run(["ok"]))
    wait_result(root, "out")
    stdout = request_dir(root, "out") / "stdout"
    size = stdout.stat().st_size
    assert size > 0
    time.sleep(0.5)
    assert stdout.stat().st_size == size


def test_public_documents_hold_no_path_pid_or_host(root, serving):
    drop(root, "r", run(["ok"]))
    drop(root, "q", {"path": "/canary/query/jobs"})
    documents = [
        (request_dir(root, "r") / "result.json", wait_result(root, "r")),
        (request_dir(root, "q") / "result.json", wait_result(root, "q")),
    ]
    documents.append((server_dir(root) / "server.json", None))
    for path, _ in documents:
        text = path.read_text()
        assert str(root.parent) not in text, path
        assert socket.gethostname() not in text, path
        assert str(os.getpid()) not in json.dumps(
            {
                k: v
                for k, v in json.loads(text).items()
                if k not in ("started", "heartbeat", "submitted", "finished")
            }
        ), path
    public = read_json(server_dir(root) / "server.json")
    assert set(public) == {
        "version",
        "state",
        "started",
        "heartbeat",
        "beat",
        "canary_version",
        "build",
        "running",
        "queued",
    }


# ---------------------------------------------------------------- rejections


@pytest.mark.parametrize(
    "envelope, status_code",
    [
        ("{not json", 400),
        ({"path": "/canary/run", "request": {"pathspec": ["ok"]}, "extra": 1}, 400),
        ({"path": "/canary/nope"}, 404),
        ({"path": "/canary/run", "request": {"pathspec": ["ok"], "wipe_workspace": True}}, 400),
        ({"path": "/canary/run", "request": {"pathspec": ["ok"]}, "cwd": "/"}, 400),
        ({"path": "/canary/run", "request": {"pathspec": ["ok"]}, "cwd": "ok/../.."}, 400),
    ],
    ids=["bad-json", "unknown-key", "unknown-route", "wipe", "absolute-cwd", "escaping-cwd"],
)
def test_a_rejected_request_ends_with_a_result(root, serving, envelope, status_code):
    drop(root, "no", envelope)
    result = wait_result(root, "no")
    assert (result["status_code"], result["state"]) == (status_code, "rejected")
    assert not (request_dir(root, "no") / "request.json").exists()


def test_a_duplicate_id_is_moved_to_rejected_and_never_runs(root, serving):
    drop(root, "twice", {"path": "/canary/status"})
    first = wait_result(root, "twice")
    drop(root, "twice", run(["failing"]))
    rejected = server_dir(root) / "rejected"
    wait_for(lambda: (rejected / "twice.json.reason").exists(), 10)
    assert "already exists" in (rejected / "twice.json.reason").read_text()
    assert json.loads((rejected / "twice.json").read_text())["path"] == "/canary/run"
    assert wait_result(root, "twice") == first


def test_a_bad_file_name_is_moved_to_rejected(root, serving):
    drop(root, "x", {"path": "/canary/status"}, name="-bad name.json")
    rejected = server_dir(root) / "rejected"
    wait_for(lambda: (rejected / "-bad name.json.reason").exists(), 10)
    assert (rejected / "-bad name.json").exists()


# ---------------------------------------------------------------- cancel, stop


def test_cancelling_a_queued_request_never_runs_it(root, serving):
    drop(root, "busy", run(["slow"]))
    wait_for(lambda: status(root, "busy").get("state") == "running")
    drop(root, "waiting", run(["ok"]))
    wait_for(lambda: status(root, "waiting").get("state") == "queued")
    cancel(root, "waiting")
    result = wait_result(root, "waiting", timeout=10)
    assert (result["state"], result["status_code"], result["started"]) == ("cancelled", 499, None)
    cancel(root, "busy")
    assert wait_result(root, "busy")["state"] == "cancelled"
    assert not (request_dir(root, "waiting") / "stdout").exists()


def test_cancelling_a_running_request_interrupts_it(root, serving):
    drop(root, "slow", run(["slow"]))
    wait_for(lambda: status(root, "slow").get("state") == "running")
    cancel(root, "slow")
    result = wait_result(root, "slow", timeout=30)
    assert (result["state"], result["status_code"]) == ("cancelled", 499)
    assert result["finished"] - result["started"] < 30


def test_stopping_the_server_fails_the_running_request_and_keeps_the_queue(root, serving):
    drop(root, "slow", run(["slow"]))
    wait_for(lambda: status(root, "slow").get("state") == "running")
    drop(root, "next", run(["ok"]))
    wait_for(lambda: status(root, "next").get("state") == "queued")
    serving.stop()
    result = read_json(request_dir(root, "slow") / "result.json")
    assert (result["state"], result["status_code"], result["error"]) == (
        "failed",
        500,
        "server stopped",
    )
    assert status(root, "next")["state"] == "queued"
    serving.start()
    assert wait_result(root, "next")["state"] == "done"


# ---------------------------------------------------------------- restart, recovery


def test_requests_dropped_while_the_server_is_down_run_in_order_once_it_starts(root):
    for name in ("c1", "c2", "c3"):
        drop(root, name, run(["ok"]))
        time.sleep(0.02)  # distinct mtimes: the inbox is taken oldest first
    serving = Serving(root).start()
    try:
        results = [wait_result(root, name) for name in ("c1", "c2", "c3")]
    finally:
        serving.stop()
    assert all(r["state"] == "done" for r in results)
    assert (
        results[0]["finished"]
        <= results[1]["started"]
        <= results[1]["finished"]
        <= results[2]["started"]
    )


def test_a_request_left_mid_accept_by_a_crash_is_settled_at_start(root, serving):
    """The server died after renaming an inbox file into accepting/ (and maybe after accept)."""
    drop(root, "done-before", {"path": "/canary/status"})
    first = wait_result(root, "done-before")
    serving.stop()
    accepting = server_dir(root) / "accepting"
    (accepting / "done-before.json").write_text(json.dumps(run(["failing"])))  # after accept
    (accepting / "never-accepted.json").write_text(json.dumps({"path": "/canary/status"}))
    serving.start()
    assert wait_result(root, "never-accepted")["state"] == "done"
    wait_for(lambda: not (accepting / "done-before.json").exists(), 10)
    assert wait_result(root, "done-before") == first  # not run again


def test_old_finished_requests_and_rejections_are_pruned_at_start(root, serving):
    drop(root, "old", {"path": "/canary/status"})
    drop(root, "-old.json", {"path": "/canary/status"}, name="-old.json")
    drop(root, "new", {"path": "/canary/status"})
    wait_result(root, "old"), wait_result(root, "new")
    rejected = server_dir(root) / "rejected"
    wait_for(lambda: (rejected / "-old.json.reason").exists(), 10)
    serving.stop()
    long_ago = time.time() - 8 * 86400
    os.utime(request_dir(root, "old") / "result.json", (long_ago, long_ago))
    for path in rejected.iterdir():
        os.utime(path, (long_ago, long_ago))
    serving.start()
    assert not request_dir(root, "old").exists() and request_dir(root, "new").exists()
    assert list(rejected.iterdir()) == []


def test_retention_is_configurable(root, monkeypatch):
    monkeypatch.setattr(
        config, "get", lambda key, default=None: 1 if key == "server:retain_days" else default
    )
    serving = Serving(root).start()
    drop(root, "a", {"path": "/canary/status"})
    wait_result(root, "a")
    serving.stop()
    two_days_ago = time.time() - 2 * 86400
    os.utime(request_dir(root, "a") / "result.json", (two_days_ago, two_days_ago))
    Serving(root).start().stop()
    assert not request_dir(root, "a").exists()
