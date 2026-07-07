# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import subprocess
from typing import Any

import pytest

from _canary.resource_pool.rpool import ResourceUnavailable
from canary_dist.adapter import DistributedResourcePoolAdapter
from canary_dist.adapter import _with_node


class FakeAdapter(DistributedResourcePoolAdapter):
    def __init__(self, *, responses: dict[str, dict[str, Any]]) -> None:
        self.server_url = "http://server"
        self.responses = responses
        self.requests: list[tuple[str, str, Any, dict[str, str]]] = []
        self.resource_counts: dict[str, dict[str, int]] = {}
        self.resource_types: list[str] = []

    def curl(
        self,
        endpoint: str,
        method: str = "POST",
        data: Any = None,
        **parameters: str,
    ) -> subprocess.CompletedProcess:
        self.requests.append((endpoint, method, data, parameters))
        payload = self.responses.get(endpoint, {"success": True})
        return subprocess.CompletedProcess(
            args=["curl"],
            returncode=0,
            stdout=__import__("json").dumps(payload),
            stderr="",
        )


def test_with_node_adds_node_to_flat_server_resources():
    resources = {
        "cpus": [{"id": "0", "slots": 1}],
        "gpus": [{"id": "0", "slots": 1}],
    }

    assert _with_node(resources, "host-a") == {
        "cpus": [{"id": "0", "slots": 1, "node": "host-a"}],
        "gpus": [{"id": "0", "slots": 1, "node": "host-a"}],
    }


def test_update_resource_counts_counts_available_slots(monkeypatch):
    monkeypatch.setattr(
        "canary.config.getoption",
        lambda name, default=None: None,
    )

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
                                "gpus": [
                                    {"id": "0", "slots": 0},
                                ],
                            },
                        },
                        {
                            "hostname": "host-b",
                            "state": "offline",
                            "resources": {
                                "cpus": [
                                    {"id": "0", "slots": 8},
                                ],
                            },
                        },
                    ]
                },
            }
        }
    )

    adapter.update_resource_counts()

    assert adapter.resource_counts == {
        "host-a": {
            "cpus": 2,
            "gpus": 0,
        }
    }
    assert adapter.resource_types == ["cpus", "gpus"]


def test_to_resource_pool_filters_offline_machines(monkeypatch):
    monkeypatch.setattr(
        "canary.config.getoption",
        lambda name, default=None: None,
    )

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
                            "resources": {
                                "cpus": [{"id": "0", "slots": 1}],
                            },
                        },
                        {
                            "hostname": "host-b",
                            "state": "offline",
                            "resources": {
                                "cpus": [{"id": "0", "slots": 1}],
                            },
                        },
                    ]
                },
            }
        }
    )

    pool = adapter.to_resource_pool()

    assert pool == {
        "allow_multinode": False,
        "additional_properties": {
            "source": "distributed",
            "server_url": "http://server",
        },
        "nodes": [
            {
                "id": "host-a",
                "resources": {
                    "cpus": [{"id": "0", "slots": 1}],
                },
                "additional_properties": {
                    "distributed": {
                        "state": "online",
                        "tags": ["gpu"],
                        "groups": ["nightly"],
                    }
                },
            }
        ],
    }


def test_checkout_returns_core_allocation(monkeypatch):
    monkeypatch.setattr(
        "canary.config.getoption",
        lambda name, default=None: None,
    )

    adapter = FakeAdapter(
        responses={
            "/rx": {"success": True},
            "/checkout": {
                "success": True,
                "hostname": "host-a",
                "transaction_id": "tx-1",
                "resources": {
                    "cpus": [{"id": "0", "slots": 1}],
                },
            },
        }
    )

    allocation = adapter.checkout([{"type": "cpus", "slots": 1}], timeout=123.0)

    assert allocation == {
        "metadata": {
            "source": "distributed",
            "server_url": "http://server",
            "hostname": "host-a",
            "transaction_id": "tx-1",
        },
        "resources": {
            "cpus": [{"id": "0", "slots": 1, "node": "host-a"}],
        },
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
    monkeypatch.setattr(
        "canary.config.getoption",
        lambda name, default=None: None,
    )

    adapter = FakeAdapter(
        responses={
            "/rx": {"success": True},
            "/checkout": {
                "success": False,
                "message": "resources unavailable",
            },
        }
    )

    with pytest.raises(ResourceUnavailable):
        adapter.checkout([{"type": "cpus", "slots": 1}])


def test_checkin_uses_transaction_id():
    adapter = FakeAdapter(
        responses={
            "/checkin": {"success": True},
        }
    )

    allocation = {
        "metadata": {
            "transaction_id": "tx-1",
        },
        "resources": {},
    }

    adapter.checkin(allocation)

    assert adapter.requests == [
        (
            "/checkin",
            "POST",
            {"transaction_id": "tx-1"},
            {},
        )
    ]


def test_checkin_requires_transaction_id():
    adapter = FakeAdapter(responses={})

    with pytest.raises(ValueError, match="transaction_id"):
        adapter.checkin({"metadata": {}, "resources": {}})
