# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""/canary/collect, /canary/select and /canary/rebaseline: _canary.app in the worker child."""

import subprocess
import sys

from _canary.service.fs.testing import drop
from _canary.service.fs.testing import run
from _canary.service.fs.testing import start_server_process
from _canary.service.fs.testing import wait_result


def _do(root, request_id, path, cwd=".", **body):
    drop(root, request_id, {"path": path, "request": body, "cwd": cwd})
    return wait_result(root, request_id)


def _names(root, request_id):
    result = _do(root, request_id, "/canary/status")
    return sorted(v["name"] for v in result["data"])


def test_collect_finds_tests_relative_to_the_requests_cwd(root, serving):
    result = _do(root, "c1", "/canary/collect", roots=["ok", "failing"])
    assert (result["state"], result["data"]) == ("done", {"collected": 2, "exit_code": 0})
    assert _names(root, "s1") == ["failing", "ok"]
    in_ok = _do(root, "c2", "/canary/collect", cwd="ok", roots=["."])
    assert in_ok["data"]["collected"] == 1


def test_collect_of_a_missing_path_is_rejected_by_the_worker(root, serving):
    result = _do(root, "c", "/canary/collect", roots=["nowhere"])
    assert (result["state"], result["status_code"]) == ("rejected", 400)
    assert "nowhere" in result["error"] and result["data"] == {"exit_code": 2}


def test_select_creates_renames_and_deletes_a_selection(root, serving):
    _do(root, "c", "/canary/collect", roots=["ok", "failing", "slow"])
    made = _do(root, "s1", "/canary/select", tag="mine", from_root=["ok"])
    assert (made["state"], made["data"]["selected"]) == ("done", 1)
    again = _do(root, "s2", "/canary/select", tag="mine")
    assert (again["state"], again["status_code"]) == ("rejected", 409)

    drop(root, "r", run(["mine"]))
    ran = wait_result(root, "r")
    assert ran["state"] == "done" and ran["data"]["exit_code"] == 0  # only ok/ ran

    renamed = _do(root, "s3", "/canary/select", tag="yours", rename_from="mine")
    assert renamed["data"]["renamed"] == "mine"
    assert _do(root, "s4", "/canary/select", tag="mine", delete=True)["status_code"] == 404
    assert _do(root, "s5", "/canary/select", tag="yours", delete=True)["state"] == "done"


def test_select_refuses_mixed_operations_before_queueing(root, serving):
    result = _do(root, "s", "/canary/select", tag="t", delete=True, keyword="fast")
    assert (result["state"], result["status_code"]) == ("rejected", 400)
    assert result["started"] is None  # never reached the worker


def test_rebaseline_reports_how_many_jobs_it_rebaselined(root, serving):
    drop(root, "r", run(["ok"]))
    assert wait_result(root, "r")["data"]["exit_code"] == 0
    result = _do(root, "b", "/canary/rebaseline", targets=["ok"])
    assert (result["state"], result["data"]) == ("done", {"rebaselined": 1, "exit_code": 0})


#: A session plugin: its collect hook leaves a mark next to itself.
MARKER_PLUGIN = """\
from pathlib import Path

import canary


@canary.hookimpl
def canary_collectstart(collector):
    (Path(__file__).parent / "collect-saw-the-plugin").touch()
"""


def test_the_worker_starts_up_as_the_server_did(root, tmp_path_factory, monkeypatch):
    """A `-p` plugin given to `canary server start` is active in the worker."""
    plugins = tmp_path_factory.mktemp("plugins")
    (plugins / "marker_plugin.py").write_text(MARKER_PLUGIN)
    monkeypatch.setenv("PYTHONPATH", str(plugins))
    srv = start_server_process(root.parent, options=["-p", "marker_plugin"])
    try:
        result = _do(root, "c", "/canary/collect", roots=["ok"])
        assert result["state"] == "done", result
    finally:
        stop = [sys.executable, "-m", "canary", "server", "stop"]
        assert subprocess.run(stop, cwd=root.parent).returncode == 0
        srv.wait(30)
    assert (plugins / "collect-saw-the-plugin").exists()
    assert not (root / "var" / "server" / "config.json").exists()  # removed at stop


def test_run_reports_canarys_exit_codes(root, serving):
    """/canary/run goes through _canary.app (no command line), with canary's exit codes."""
    drop(root, "r1", run(["ok"]))
    assert wait_result(root, "r1")["data"] == {"exit_code": 0}
    drop(root, "r2", run(["ok"]))  # passed already: nothing to run
    second = wait_result(root, "r2")
    assert (second["state"], second["data"]) == ("done", {"exit_code": 7})
    drop(root, "r3", run(["failing"]))
    assert wait_result(root, "r3")["data"]["exit_code"] not in (0, 7)


def test_run_values_an_option_refuses_are_rejected(root, serving):
    drop(root, "bad", run(["ok"], timeout="session=not-a-time"))
    result = wait_result(root, "bad")
    assert (result["state"], result["status_code"]) == ("rejected", 400), result
    assert "timeout" in result["error"]


def test_plain_commands_never_load_the_api_models():
    """Endpoints register lazily: pydantic costs ~100 ms on canary's start-up."""
    probe = (
        "import sys\n"
        "from _canary import config\n"
        "config.pluginmanager.hook.canary_addcommand\n"
        "print('pydantic' in sys.modules)\n"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stderr


def test_hpc_run_goes_through_canary_hpcs_application_layer(root, serving):
    """/canary/hpc/run calls canary_hpc.app.run, as `canary hpc run` does (local backend)."""
    drop(
        root, "h1", {"path": "/canary/hpc/run", "request": {"pathspec": ["ok"], "backend": "local"}}
    )
    result = wait_result(root, "h1")
    assert (result["state"], result["data"]) == ("done", {"exit_code": 0}), result
    drop(
        root,
        "h2",
        {"path": "/canary/hpc/run", "request": {"pathspec": ["failing"], "backend": "local"}},
    )
    assert wait_result(root, "h2")["data"]["exit_code"] not in (0, 7)
