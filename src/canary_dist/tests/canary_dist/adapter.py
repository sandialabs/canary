# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import subprocess
from typing import Any
from typing import cast

import pytest

import canary
from _canary.resource_pool.rpool import NodeRequest
from _canary.resource_pool.rpool import Outcome
from _canary.resource_pool.rpool import ResourceUnavailable
from canary_dist.adapter import DistributedResourcePoolAdapter
from canary_dist.adapter import _with_node


def counted_node_request(**counts: int) -> NodeRequest:
    req = NodeRequest()
    for rtype, count in counts.items():
        req.add(rtype, count)
    return req


class FakeAdapter(DistributedResourcePoolAdapter):
    def __init__(self, *, responses: dict[str, dict[str, Any]]) -> None:
        self.server_url = "http://server"
        self.responses = responses
        self.requests: list[tuple[str, str, Any, dict[str, str]]] = []
        self.resource_counts: dict[str, dict[str, int]] = {}
        self.resource_types: list[str] = []

    def curl(
        self, endpoint: str, method: str = "POST", data: Any = None, **parameters: str
    ) -> subprocess.CompletedProcess:
        self.requests.append((endpoint, method, data, parameters))
        payload = self.responses.get(endpoint, {"success": True})
        return subprocess.CompletedProcess(
            args=["curl"], returncode=0, stdout=__import__("json").dumps(payload), stderr=""
        )


def test_with_node_adds_node_to_flat_server_resources():
    resources = {"cpus": [{"id": "0", "slots": 1}], "gpus": [{"id": "0", "slots": 1}]}

    assert _with_node(resources, "host-a") == {
        "cpus": [{"id": "0", "slots": 1, "node": "host-a"}],
        "gpus": [{"id": "0", "slots": 1, "node": "host-a"}],
    }


def test_update_resource_counts_counts_available_slots(monkeypatch):
    monkeypatch.setattr("canary.config.getoption", lambda name, default=None: None)

    adapter = FakeAdapter(
        responses={
            "/status": {
                "success": True,
                "database": {
                    "machines": [
                        {
                            "hostname": "host-a",
                            "state": "online",
                            "resources": {
                                "cpus": [
                                    {"id": "0", "slots": 1},
                                    {"id": "1", "slots": 0},
                                    {"id": "2", "slots": 1},
                                ],
                                "gpus": [{"id": "0", "slots": 0}],
                            },
                        },
                        {
                            "hostname": "host-b",
                            "state": "offline",
                            "resources": {"cpus": [{"id": "0", "slots": 8}]},
                        },
                    ]
                },
            }
        }
    )

    adapter.update_resource_counts()

    assert adapter.resource_counts == {"host-a": {"cpus": 2, "gpus": 0}}
    assert adapter.resource_types == ["cpus", "gpus"]


def test_to_resource_pool_filters_offline_machines(monkeypatch):
    monkeypatch.setattr("canary.config.getoption", lambda name, default=None: None)

    adapter = FakeAdapter(
        responses={
            "/status": {
                "success": True,
                "database": {
                    "machines": [
                        {
                            "hostname": "host-a",
                            "state": "online",
                            "tags": ["gpu"],
                            "groups": ["nightly"],
                            "resources": {"cpus": [{"id": "0", "slots": 1}], "gpus": []},
                        },
                        {
                            "hostname": "host-b",
                            "state": "offline",
                            "resources": {"cpus": [{"id": "0", "slots": 1}], "gpus": []},
                        },
                    ]
                },
            }
        }
    )

    pool = adapter.to_resource_pool()

    assert pool == {
        "allow_multinode": False,
        "additional_properties": {"source": "canary-dist", "server_url": "http://server"},
        "nodes": [
            {
                "id": "host-a",
                "resources": {"cpus": [{"id": "0", "slots": 1}], "gpus": []},
                "additional_properties": {
                    "distributed": {"state": "online", "tags": ["gpu"], "groups": ["nightly"]}
                },
            }
        ],
    }


def test_checkout_returns_core_allocation(monkeypatch):
    monkeypatch.setattr("canary.config.getoption", lambda name, default=None: None)

    adapter = FakeAdapter(
        responses={
            "/rx": {"success": True},
            "/checkout": {
                "success": True,
                "hostname": "host-a",
                "transaction_id": "tx-1",
                "resources": {"cpus": [{"id": "0", "slots": 1}]},
            },
        }
    )

    allocation = adapter.checkout([counted_node_request(cpus=1)], timeout=123.0)

    assert allocation == {
        "metadata": {
            "source": "canary-dist",
            "server_url": "http://server",
            "hostname": "host-a",
            "transaction_id": "tx-1",
        },
        "resources": {"cpus": [{"id": "0", "slots": 1, "node": "host-a"}]},
    }

    assert adapter.requests[0][0] == "/rx"
    assert adapter.requests[1] == (
        "/checkout",
        "POST",
        {
            "resources": [{"type": "cpus", "slots": 1}],
            "timeout": 123.0,
            "tags": None,
            "groups": None,
        },
        {},
    )


def test_checkout_raises_when_server_reports_unavailable(monkeypatch):
    monkeypatch.setattr("canary.config.getoption", lambda name, default=None: None)

    adapter = FakeAdapter(
        responses={
            "/rx": {"success": True},
            "/checkout": {"success": False, "message": "resources unavailable"},
        }
    )

    with pytest.raises(ResourceUnavailable):
        adapter.checkout([counted_node_request(cpus=1)])


def test_checkout_maps_transport_failures_to_resource_unavailable(monkeypatch):
    monkeypatch.setattr("canary.config.getoption", lambda name, default=None: None)

    adapter = FakeAdapter(responses={"/rx": {"success": True}})

    def failing_curl(endpoint: str, method: str = "POST", data: Any = None, **parameters: str):
        if endpoint == "/checkout":
            return subprocess.CompletedProcess(
                args=["curl"], returncode=28, stdout="", stderr="timed out"
            )
        return FakeAdapter.curl(adapter, endpoint, method, data, **parameters)

    monkeypatch.setattr(adapter, "curl", failing_curl)

    with pytest.raises(ResourceUnavailable, match="timed out"):
        adapter.checkout([counted_node_request(cpus=1)])


def test_current_state_maps_transport_failures_to_resource_unavailable(monkeypatch):
    monkeypatch.setattr("canary.config.getoption", lambda name, default=None: None)

    adapter = FakeAdapter(responses={})

    def failing_curl(endpoint: str, method: str = "POST", data: Any = None, **parameters: str):
        return subprocess.CompletedProcess(
            args=["curl"], returncode=7, stdout="", stderr="connection refused"
        )

    monkeypatch.setattr(adapter, "curl", failing_curl)

    with pytest.raises(ResourceUnavailable, match="connection refused"):
        adapter.current_state()


def test_accommodates_remote_returns_negative_outcome_on_transport_failure(monkeypatch):
    monkeypatch.setattr("canary.config.getoption", lambda name, default=None: None)

    class FakeCase:
        def required_resources(self):
            return [counted_node_request(cpus=1)]

    adapter = FakeAdapter(responses={})

    def failing_curl(endpoint: str, method: str = "POST", data: Any = None, **parameters: str):
        return subprocess.CompletedProcess(
            args=["curl"], returncode=56, stdout="", stderr="recv failure"
        )

    monkeypatch.setattr(adapter, "curl", failing_curl)

    outcome = adapter.accommodates_remote(cast(canary.TestCase, FakeCase()))

    assert isinstance(outcome, Outcome)
    assert outcome.ok is False
    assert outcome.reason == "recv failure"


def test_curl_sets_connect_and_request_timeouts(monkeypatch):
    monkeypatch.setattr("canary.config.getoption", lambda name, default=None: None)
    monkeypatch.setattr(DistributedResourcePoolAdapter, "update_resource_counts", lambda self: None)

    called: dict[str, Any] = {}

    def fake_run(args, capture_output, text):
        called["args"] = args
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout='{"success": true}', stderr=""
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    adapter = DistributedResourcePoolAdapter(server_url="http://server")
    adapter.curl("/status", method="GET")

    assert "--connect-timeout" in called["args"]
    assert "--max-time" in called["args"]


def test_checkin_uses_transaction_id():
    adapter = FakeAdapter(responses={"/checkin": {"success": True}})

    allocation = {"metadata": {"transaction_id": "tx-1"}, "resources": {}}

    adapter.checkin(allocation)

    assert adapter.requests == [("/checkin", "POST", {"transaction_id": "tx-1"}, {})]


def test_checkin_requires_transaction_id():
    adapter = FakeAdapter(responses={})

    with pytest.raises(ValueError, match="transaction_id"):
        adapter.checkin({"metadata": {}, "resources": {}})


def test_max_capacity_by_type_uses_resource_counts(monkeypatch):
    from canary_dist.adapter import DistributedResourcePoolAdapter

    def fake_update(self):
        self.resource_counts = {"host-a": {"cpus": 8, "gpus": 1}, "host-b": {"cpus": 16, "gpus": 4}}
        self.resource_types = ["cpus", "gpus"]

    monkeypatch.setattr(DistributedResourcePoolAdapter, "update_resource_counts", fake_update)
    monkeypatch.setattr(
        DistributedResourcePoolAdapter, "current_state", lambda self: {"database": {"machines": []}}
    )

    adapter = DistributedResourcePoolAdapter(server_url="http://server")

    assert adapter.max_capacity_by_type() == {"cpus": 16, "gpus": 4}
