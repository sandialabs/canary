# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import types
from typing import Any
from typing import cast

import canary_flux


class FakeConfig:
    def __init__(self, options):
        self.options = dict(options)

    def getoption(self, name, default=None):
        return self.options.get(name, default)


class FakeBackend:
    name = "flux"

    def __init__(self, counts=None, resource_types=None, node_count=2):
        self._counts = counts or {"cpus": 8, "gpus": 2}
        self._resource_types = resource_types or ["cpus", "gpus"]
        self._node_count = node_count

    def resource_types(self):
        return list(self._resource_types)

    def count_per_node(self, rtype):
        if rtype in self._counts:
            return self._counts[rtype]
        if rtype.endswith("s") and rtype[:-1] in self._counts:
            return self._counts[rtype[:-1]]
        if not rtype.endswith("s") and f"{rtype}s" in self._counts:
            return self._counts[f"{rtype}s"]
        raise ValueError(rtype)

    def count(self, rtype):
        if rtype in ("node", "nodes"):
            return self._node_count
        raise ValueError(rtype)


def test_resource_pool_fill_inactive_returns_none():
    config = FakeConfig({"flux_direct_run": False})

    assert canary_flux.canary_resource_pool_fill(cast(Any, config)) is None


def test_resource_pool_fill_ignored_for_flux_exec():
    config = FakeConfig({"flux_direct_run": True, "flux_exec": True})

    assert canary_flux.canary_resource_pool_fill(cast(Any, config)) is None


def test_resource_pool_fill_uses_fake_hpc_connect(monkeypatch):
    backend = FakeBackend(counts={"cpus": 16, "gpus": 4}, node_count=3)

    fake_hpc_connect = types.SimpleNamespace(get_backend=lambda name: backend)

    monkeypatch.setitem(__import__("sys").modules, "hpc_connect", fake_hpc_connect)

    config = FakeConfig({"flux_direct_run": True, "flux_exec": False, "flux_backend": "flux"})

    pool = canary_flux.canary_resource_pool_fill(cast(Any, config))

    assert pool is not None
    assert pool["allow_multinode"] is True
    assert pool["additional_properties"]["source"] == "canary_flux"
    assert pool["additional_properties"]["backend"] == "flux"
    assert pool["additional_properties"]["node_count"] == 3
    assert pool["additional_properties"]["cpus_per_node"] == 16
    assert pool["additional_properties"]["gpus_per_node"] == 4

    assert len(pool["nodes"]) == 3

    for node in pool["nodes"]:
        assert len(node["resources"]["cpus"]) == 16
        assert len(node["resources"]["gpus"]) == 4
        assert node["resources"]["cpus"][0] == {"id": "0", "slots": 1}
        assert node["resources"]["gpus"][0]["properties"]["vendor"] == "UNKNOWN"


def test_resource_helpers_pluralization():
    assert canary_flux._canonical_resource_type("cpu") == "cpus"
    assert canary_flux._canonical_resource_type("cpus") == "cpus"
    assert canary_flux._singular_resource_type("gpus") == "gpu"
    assert canary_flux._singular_resource_type("gpu") == "gpu"


def test_allocation_node_count_uses_max_cli_or_job(monkeypatch):
    class FakeJob:
        def __init__(self, n):
            self.n = n

        def required_resources(self):
            return [object() for _ in range(self.n)]

    class FakeConfig:
        def getoption(self, name, default=None):
            if name == "flux_nodes":
                return 4
            return default

    monkeypatch.setattr(canary_flux.canary, "config", FakeConfig())

    jobs = [FakeJob(1), FakeJob(2), FakeJob(3)]

    assert canary_flux._allocation_node_count(cast(Any, jobs)) == 4


def test_allocation_node_count_uses_job_max_when_cli_none(monkeypatch):
    class FakeJob:
        def __init__(self, n):
            self.n = n

        def required_resources(self):
            return [object() for _ in range(self.n)]

    class FakeConfig:
        def getoption(self, name, default=None):
            return None if name == "flux_nodes" else default

    monkeypatch.setattr(canary_flux.canary, "config", FakeConfig())

    jobs = [FakeJob(1), FakeJob(5), FakeJob(2)]

    assert canary_flux._allocation_node_count(cast(Any, jobs)) == 5
