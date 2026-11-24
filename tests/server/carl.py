# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""carl: the curl-like client `canary server start` installs, run with only /usr/bin:/bin."""

import json
import os
import signal
import subprocess

import pytest

from _canary.service.fs.testing import Serving
from _canary.service.fs.testing import request_dir
from _canary.service.fs.testing import server_dir
from _canary.service.fs.testing import status
from _canary.service.fs.testing import wait_for

CLEAN_ENV = {"PATH": "/usr/bin:/bin"}


@pytest.fixture
def carl(root, serving):
    """Run the installed carl with nothing but /usr/bin:/bin; returns (code, stdout, stderr)."""
    script = root / "share" / "carl"

    def carl(*args, timeout=180):
        proc = subprocess.run(
            [str(script), *args], capture_output=True, text=True, env=CLEAN_ENV, timeout=timeout
        )
        return proc.returncode, proc.stdout, proc.stderr

    return carl


def _url(root, route=""):
    return f"file://{root.parent}{route}"


def test_the_server_installs_an_executable_carl(root, serving):
    script = root / "share" / "carl"
    assert script.is_file() and os.access(script, os.X_OK)
    help_ = subprocess.run([str(script), "--help"], capture_output=True, text=True, env=CLEAN_ENV)
    assert help_.returncode == 0 and "usage: carl" in help_.stdout
    assert "/canary/help" in help_.stdout  # where to find every route


def test_post_a_run_waits_and_prints_the_result(root, carl):
    code, out, err = carl("POST", _url(root, "/canary/run"), "-d", '{"pathspec": ["ok"]}')
    assert code == 0, err
    result = json.loads(out)
    assert (result["state"], result["path"], result["data"]) == (
        "done",
        "/canary/run",
        {"exit_code": 0},
    )
    assert "submitted carl-" in err


def test_put_a_whole_envelope_with_an_id_cwd_and_env(root, carl, tmp_path):
    body = tmp_path / "envelope.json"
    body.write_text(
        json.dumps(
            {"path": "/canary/run", "request": {"pathspec": ["."], "only": "all"}, "cwd": "ok"}
        )
    )
    code, out, _ = carl("PUT", _url(root), "-d", f"@{body}", "-H", "Idempotency-Key: mine", "-s")
    assert code == 0 and json.loads(out)["cwd"] == "ok"
    assert "1 pass" in (request_dir(root, "mine") / "stdout").read_text()
    code, out, _ = carl(
        "POST", _url(root, "/canary/status"), "--cwd", "ok", "--env", 'A=b "c"', "-s"
    )
    assert code == 0 and json.loads(out)["state"] == "done"


def test_reads_and_gets(root, carl):
    code, out, _ = carl("POST", _url(root, "/canary/schema"), "-H", "Idempotency-Key: s1", "-s")
    assert code == 0 and "/canary/run" in json.loads(out)["data"]["endpoints"]
    code, out, _ = carl("GET", _url(root, "/requests/s1"))
    assert code == 0 and json.loads(out)["id"] == "s1"
    code, out, _ = carl("GET", _url(root, "/server"))
    assert code == 0 and json.loads(out)["state"] == "running"
    code, _, err = carl("GET", _url(root, "/requests/nope"))
    assert code == 22 and "no request nope" in err


def test_get_submits_reads_and_work_refuses_it(root, carl):
    code, out, _ = carl("GET", _url(root, "/canary/help"), "-s")
    assert code == 0 and out.endswith("}\n")  # the prompt starts on its own line
    assert "/canary/run" in json.loads(out)["data"]["endpoints"]
    code, out, _ = carl("GET", _url(root, "/canary/run"), "-s", "-d", '{"pathspec": ["ok"]}')
    result = json.loads(out)
    assert (result["status_code"], result["state"]) == (405, "rejected"), result
    code, _, err = carl("GET", _url(root, "/help"), "-s")  # routes are under /canary/
    assert code == 2 and "/canary/ROUTE" in err
    code, out, _ = carl("POST", _url(root, "/help"), "-s")
    assert "/canary/help lists every route" in json.loads(out)["error"]


def test_fail_turns_an_error_result_into_exit_22(root, carl):
    code, out, _ = carl("POST", _url(root, "/canary/no-such-route"), "-s")
    assert (
        code == 0 and json.loads(out)["status_code"] == 404
    )  # like curl: a response is a response
    code, out, _ = carl("POST", _url(root, "/canary/no-such-route"), "-s", "-f")
    assert code == 22 and json.loads(out)["status_code"] == 404


def test_cancel_from_another_carl(root, carl):
    script = root / "share" / "carl"
    waiting = subprocess.Popen(
        [
            str(script),
            "POST",
            _url(root, "/canary/run"),
            "-d",
            '{"pathspec": ["slow"]}',
            "-H",
            "Idempotency-Key: slow1",
            "-s",
        ],
        stdout=subprocess.PIPE,
        text=True,
        env=CLEAN_ENV,
    )
    wait_for(lambda: status(root, "slow1").get("state") == "running")
    code, _, err = carl("POST", _url(root, "/requests/slow1/cancel"))
    assert code == 0, err
    out, _ = waiting.communicate(timeout=60)
    assert waiting.returncode == 0 and json.loads(out)["state"] == "cancelled"


def test_ctrl_c_cancels_the_request(root, carl):
    script = root / "share" / "carl"
    waiting = subprocess.Popen(
        [
            str(script),
            "POST",
            _url(root, "/canary/run"),
            "-d",
            '{"pathspec": ["slow"]}',
            "-H",
            "Idempotency-Key: slow2",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=CLEAN_ENV,
    )
    wait_for(lambda: status(root, "slow2").get("state") == "running")
    waiting.send_signal(signal.SIGINT)
    out, err = waiting.communicate(timeout=60)
    assert waiting.returncode == 130, err
    assert json.loads(out)["state"] == "cancelled" and "cancelling slow2" in err


def test_max_time_stops_waiting_and_the_request_goes_on(root, carl):
    code, _, err = carl(
        "POST",
        _url(root, "/canary/run"),
        "-d",
        '{"pathspec": ["slow"]}',
        "-H",
        "Idempotency-Key: slow3",
        "-m",
        "1",
    )
    assert code == 28 and "timed out" in err
    assert status(root, "slow3")["state"] in ("queued", "running")
    (request_dir(root, "slow3") / "cancel").touch()


@pytest.mark.parametrize(
    "args, code, message",
    [
        (["POST"], 2, "usage"),
        (["DELETE", "file:///x"], 2, "unsupported method"),
        (["POST", "http://host/canary/run"], 2, "only file://"),
        (["POST", "file:///nowhere/at/all/canary/run"], 6, "no canary workspace"),
        (["POST", "{url}/canary/run", "-d", "[1]"], 2, "JSON object"),
        (["POST", "{url}", "-d", '{"path": "/canary/status"}', "--cwd", "ok"], 2, "--cwd/--env"),
        (["POST", "{url}/canary/status", "-H", "Idempotency-Key: -bad"], 2, "invalid request id"),
        (["POST", "{url}/canary/status", "-H", "X-Other: 1"], 2, "unsupported header"),
    ],
)
def test_usage_errors(root, carl, args, code, message):
    args = [a.replace("{url}", _url(root)) for a in args]
    got, _, err = carl(*args)
    assert got == code and message in err, err


def test_no_server_is_exit_7(root):
    serving = Serving(root).start()  # installs carl
    serving.stop()
    proc = subprocess.run(
        [str(root / "share" / "carl"), "POST", _url(root, "/canary/status")],
        capture_output=True,
        text=True,
        env=CLEAN_ENV,
    )
    assert proc.returncode == 7 and "no canary server is running" in proc.stderr
    assert not list((server_dir(root) / "inbox").iterdir())  # nothing was queued
