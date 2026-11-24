# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""accept(): routing, validation, the result document, and queueing work."""

import json
import os
import threading
import time

import pytest
from pydantic import BaseModel
from pydantic import ConfigDict

import canary
from _canary.api import requests
from _canary.api.dispatch import Context
from _canary.api.dispatch import EndpointRegistry
from _canary.api.dispatch import RequestError
from _canary.api.dispatch import accept
from _canary.api.models import Result
from _canary.api.requests import write_result
from _canary.plugins.hookspec import hookimpl
from _canary.service.fs import server
from _canary.workspace.workspace import Workspace

PASSING = 'import sys\nif __name__ == "__main__":\n    sys.exit(0)\n'
FAILING = 'import sys\nif __name__ == "__main__":\n    sys.exit(1)\n'


@pytest.fixture
def root(tmp_path):
    """A workspace's root, with ok/ and failing/ test directories under its anchor."""
    for name, body in (("ok", PASSING), ("failing", FAILING)):
        (tmp_path / name).mkdir()
        (tmp_path / name / f"{name}.pyt").write_text(body)
    return Workspace.create(tmp_path).root


def _accept(root, request_id, envelope, **kwargs):
    return accept(request_id, envelope, user="alice", workspace_root=root, **kwargs)


def _result(root, request_id):
    return json.loads((requests.request_dir(root, request_id) / "result.json").read_text())


class Echo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int = 0


@pytest.fixture
def registry():
    def echo(request: Echo, ctx: Context) -> dict:
        if request.value < 0:
            raise RequestError(404, "nothing below zero")
        if request.value == 13:
            raise RuntimeError("unlucky")
        return {"value": request.value, "cwd": ctx.cwd, "user": ctx.user}

    registry = EndpointRegistry()
    registry.register("/test/echo", echo)
    return registry


# ---------------------------------------------------------------- registry


def test_the_request_model_comes_from_the_handlers_annotation(registry):
    endpoint = registry.get("/test/echo")
    assert endpoint is not None and endpoint.model is Echo and endpoint.lane == "read"


def test_a_handler_without_a_model_a_second_handler_or_a_bad_lane_is_refused(registry):
    def untyped(request, ctx): ...

    def again(request: Echo, ctx: Context): ...

    with pytest.raises(TypeError):
        registry.register("/test/untyped", untyped)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("/test/echo", again)
    with pytest.raises(ValueError, match="lane"):
        registry.register("/test/other", again, lane="fast")


def test_core_and_plugins_register_through_the_hook():
    from _canary.api.dispatch import build_registry

    endpoints = {e.path: e for e in build_registry()}
    assert endpoints["/canary/status"].lane == "read"
    assert endpoints["/canary/run"].lane == "work"
    assert endpoints["/canary/hpc/run"].func.__module__ == "canary_hpc.endpoint"


class _Plugin:
    @hookimpl(specname="canary_addendpoint")
    def extra(self, registry):
        def hello(request: Echo, ctx: Context) -> dict:
            return {"hello": request.value}

        registry.register("/plugin/hello", hello)


def test_a_plugins_endpoint_is_served(root):
    pm = canary.config.pluginmanager
    pm.register(_Plugin(), name="test_plugin_endpoint")
    try:
        result = _accept(root, "hi", {"path": "/plugin/hello", "request": {"value": 7}})
        assert (result.state, result.data) == ("done", {"hello": 7})

        class _Clash:
            @hookimpl(specname="canary_addendpoint")
            def clash(self, registry):
                def status(request: Echo, ctx: Context) -> dict: ...

                registry.register("/canary/status", status)

        pm.register(_Clash(), name="test_plugin_clash")
        from _canary.api.dispatch import build_registry

        with pytest.raises(ValueError, match="already registered .*_canary.api.status"):
            build_registry()
    finally:
        for name in ("test_plugin_endpoint", "test_plugin_clash"):
            if pm.get_plugin(name) is not None:
                pm.unregister(name=name)


# ---------------------------------------------------------------- read lane


def test_a_read_ends_done_with_its_data_and_the_servers_facts(root, registry):
    (root.parent / "ok" / "sub").mkdir()
    result = _accept(
        root,
        "r1",
        {"path": "/test/echo", "request": {"value": 3}, "cwd": "ok/sub"},
        registry=registry,
    )
    assert result is not None and result.status_code == 200 and result.state == "done"
    on_disk = _result(root, "r1")
    assert on_disk == json.loads(result.model_dump_json())
    assert on_disk["data"] == {"value": 3, "cwd": "ok/sub", "user": "alice"}
    assert on_disk["id"] == "r1" and on_disk["path"] == "/test/echo" and on_disk["version"] == 1
    assert on_disk["submitted"] <= on_disk["started"] <= on_disk["finished"]
    status = requests.read_status(requests.request_dir(root, "r1"))
    assert status["state"] == "done"


def test_handler_errors_become_status_codes(root, registry):
    missing = _accept(
        root, "neg", {"path": "/test/echo", "request": {"value": -1}}, registry=registry
    )
    crashed = _accept(
        root, "bad", {"path": "/test/echo", "request": {"value": 13}}, registry=registry
    )
    assert (missing.status_code, missing.state, missing.error) == (
        404,
        "rejected",
        "nothing below zero",
    )
    assert (crashed.status_code, crashed.state) == (500, "failed")
    assert "unlucky" in crashed.error
    assert _result(root, "bad")["status_code"] == 500


# ---------------------------------------------------------------- rejection


@pytest.mark.parametrize(
    "envelope, status_code, message",
    [
        ("not json", 400, "invalid JSON"),
        (b'{"path": "/test/echo", "request": {"value": 2}', 400, "invalid JSON"),
        ([1, 2], 400, "invalid envelope"),
        ({"request": {}}, 400, "path"),
        ({"path": "/test/echo", "user": "mallory"}, 400, "user"),
        ({"path": "/test/echo", "version": 2}, 400, "version"),
        ({"path": "/test/echo", "env": {"N": 1}}, 400, "env"),
        ({"path": "/test/nope"}, 404, "no endpoint"),
        ({"path": "/test/echo", "request": {"value": "x"}}, 400, "value"),
        ({"path": "/test/echo", "request": {"other": 1}}, 400, "other"),
        ({"path": "/test/echo", "cwd": "/usr"}, 400, "relative"),
        ({"path": "/test/echo", "cwd": "ok/../.."}, 400, "relative"),
        ({"path": "/test/echo", "cwd": "missing"}, 400, "not a directory"),
    ],
)
def test_rejections_end_with_a_result(root, registry, envelope, status_code, message):
    result = _accept(root, "req", envelope, registry=registry)
    assert result is not None and (result.status_code, result.state) == (status_code, "rejected")
    assert message in result.error
    assert _result(root, "req")["status_code"] == status_code


def test_a_cwd_that_leads_outside_the_anchor_through_a_symlink_is_rejected(
    root, registry, tmp_path_factory
):
    outside = tmp_path_factory.mktemp("outside")
    os.symlink(outside, root.parent / "link")
    result = _accept(root, "req", {"path": "/test/echo", "cwd": "link"}, registry=registry)
    assert result.status_code == 400 and "outside the anchor" in result.error


def test_a_duplicate_id_gets_409_and_leaves_the_first_alone(root, registry):
    first = _accept(root, "dup", {"path": "/test/echo", "request": {"value": 1}}, registry=registry)
    second = _accept(
        root, "dup", {"path": "/test/echo", "request": {"value": 2}}, registry=registry
    )
    assert second.status_code == 409 and second.state == "rejected"
    assert _result(root, "dup") == json.loads(first.model_dump_json())


@pytest.mark.parametrize("request_id", ["", ".hidden", "a/b", "x" * 129, "-x", 7])
def test_an_invalid_id_is_refused_and_writes_nothing(root, registry, request_id):
    with pytest.raises(ValueError, match="invalid request id"):
        _accept(root, request_id, {"path": "/test/echo"}, registry=registry)
    assert not (server.server_dir(root) / "requests").exists()


def test_a_result_is_written_once(root, registry):
    _accept(root, "once", {"path": "/test/echo"}, registry=registry)
    again = Result(
        id="once",
        path="/test/echo",
        status_code=200,
        state="done",
        cwd=".",
        user="a",
        submitted=0,
        finished=0,
    )
    with pytest.raises(RuntimeError, match="already has a result"):
        write_result(requests.request_dir(root, "once"), again)


# ---------------------------------------------------------------- work lane


def test_a_work_request_is_queued_with_its_validated_body(root):
    envelope = {
        "path": "/canary/run",
        "request": {"pathspec": ["ok"], "workers": 1},
        "env": {"X": "1"},
    }
    assert _accept(root, "w1", envelope) is None
    directory = requests.request_dir(root, "w1")
    record = requests.read_request(directory)
    assert record["path"] == "/canary/run" and record["request"]["workers"] == 1
    assert record["env"] == {"X": "1"} and record["user"] == "alice" and record["cwd"] == "."
    assert requests.read_status(directory)["state"] == "queued"
    assert requests.queued_ids(root) == ["w1"]
    assert not (directory / "result.json").exists()


def test_a_work_request_with_a_bad_body_is_rejected_before_queueing(root):
    result = _accept(
        root, "w2", {"path": "/canary/run", "request": {"pathspec": ["ok"], "only": "bogus"}}
    )
    assert result.status_code == 400 and "only" in result.error
    assert requests.queued_ids(root) == []


def test_queued_work_runs_on_the_server_in_order(root, monkeypatch):
    monkeypatch.setattr(server, "TICK", 0.05)
    for request_id, path in (("a", "failing"), ("b", "ok")):
        assert (
            _accept(root, request_id, {"path": "/canary/run", "request": {"pathspec": [path]}})
            is None
        )
    srv = server.Server(root)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 120
        states = {}
        while time.time() < deadline:
            states = {i: requests.read_status(requests.request_dir(root, i)) for i in "ab"}
            if all(s.get("state") in requests.TERMINAL_STATES for s in states.values()):
                break
            time.sleep(0.1)
        assert [states[i].get("state") for i in "ab"] == ["done", "done"], states
        assert states["a"]["returncode"] != 0 and states["b"]["returncode"] == 0
        assert states["a"]["finished"] <= states["b"]["started"]
    finally:
        srv.request_stop()
        thread.join(30)


def test_the_server_logs_each_result_in_one_line():
    from _canary.api.requests import access_line

    work = Result(
        id="r1", path="/canary/run", status_code=200, state="done", data={"exit_code": 14},
        cwd=".", user="u", submitted=1.0, started=2.0, finished=5.5,
    )  # fmt: skip
    assert access_line(work) == "[bold]200[/] /canary/run r1 (u) done in 3.5s, exit code 14"
    bad = Result(
        id="r2", path="/canary/nope", status_code=404, state="rejected", error="no endpoint",
        cwd=".", user="u", submitted=1.0, finished=1.0,
    )  # fmt: skip
    assert access_line(bad) == "[bold]404[/] /canary/nope r2 (u) rejected in 0.0s: no endpoint"
