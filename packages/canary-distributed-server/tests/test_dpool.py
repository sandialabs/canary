# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Tests for DistributedResourcePool (multi-machine layer)."""

import json
from pathlib import Path

import pytest

from canary_distributed_server.dpool import DistributedResourcePool
from canary_distributed_server.dpool import MachineResourcePool
from canary_distributed_server.rpool import ResourceUnavailable

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_poolfile(tmp_path: Path, machines: list[dict] | None = None) -> Path:
    """Write a pool.json and return its path."""
    db = {"machines": machines or []}
    p = tmp_path / "pool.json"
    p.write_text(json.dumps(db))
    return p


def machine(
    hostname: str,
    cpus: int = 4,
    gpus: int = 0,
    state: str = "online",
    tags: list[str] | None = None,
    groups: list[str] | None = None,
) -> dict:
    resources: dict = {"cpus": [{"id": str(i), "slots": 1} for i in range(cpus)]}
    if gpus:
        resources["gpus"] = [{"id": str(i), "slots": 1} for i in range(gpus)]
    m: dict = {"hostname": hostname, "resources": resources, "state": state}
    if tags:
        m["tags"] = tags
    if groups:
        m["groups"] = groups
    return m


def req(cpus: int = 1, gpus: int = 0) -> list[dict]:
    r = [{"type": "cpus", "slots": 1} for _ in range(cpus)]
    r += [{"type": "gpus", "slots": 1} for _ in range(gpus)]
    return r


# ---------------------------------------------------------------------------
# MachineResourcePool.score
# ---------------------------------------------------------------------------


class TestMachineResourcePoolScore:
    def test_score_zero_when_fully_consumed(self):
        pool = MachineResourcePool({"cpus": [{"id": "0", "slots": 0}]})
        score = pool.score({"cpus": [{"id": "0", "slots": 1}]})
        assert score == 0.0

    def test_score_higher_with_more_free_slots(self):
        pool_a = MachineResourcePool({"cpus": [{"id": str(i), "slots": 1} for i in range(8)]})
        pool_b = MachineResourcePool({"cpus": [{"id": str(i), "slots": 1} for i in range(4)]})
        acquired = {"cpus": [{"id": "0", "slots": 1}]}
        # Pool A has 8 CPUs, pool B has 4 — after same checkout, A should score higher
        assert pool_a.score(acquired) > pool_b.score(acquired)


# ---------------------------------------------------------------------------
# DistributedResourcePool: construction and persistence
# ---------------------------------------------------------------------------


class TestDistributedPoolConstruction:
    def test_creates_empty_pool_if_no_file(self, tmp_path):
        p = tmp_path / "pool.json"
        assert not p.exists()
        pool = DistributedResourcePool(p)
        assert pool.empty()
        assert p.exists()

    def test_loads_existing_pool(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01")])
        pool = DistributedResourcePool(p)
        assert not pool.empty()
        assert len(pool.db["machines"]) == 1

    def test_rejects_duplicate_hostnames(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01"), machine("worker01")])
        with pytest.raises(ValueError):
            DistributedResourcePool(p)

    def test_save_is_atomic(self, tmp_path):
        """save() must not leave a .tmp file behind."""
        p = make_poolfile(tmp_path)
        pool = DistributedResourcePool(p)
        pool.save()
        assert not (tmp_path / "pool.tmp").exists()
        assert p.exists()

    def test_save_roundtrip(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01", cpus=8)])
        pool = DistributedResourcePool(p)
        pool.save()
        pool2 = DistributedResourcePool(p)
        assert len(pool2.db["machines"]) == 1
        assert pool2.db["machines"][0]["hostname"] == "worker01"


# ---------------------------------------------------------------------------
# DistributedResourcePool.add / pop
# ---------------------------------------------------------------------------


class TestAddAndPop:
    def test_add_machine(self, tmp_path):
        p = make_poolfile(tmp_path)
        pool = DistributedResourcePool(p)
        pool.add("worker01", [{"type": "cpus", "count": 4}])
        assert len(pool.db["machines"]) == 1
        assert pool.db["machines"][0]["hostname"] == "worker01"
        assert len(pool.db["machines"][0]["resources"]["cpus"]) == 4

    def test_add_duplicate_raises(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01")])
        pool = DistributedResourcePool(p)
        with pytest.raises(ValueError, match="already in"):
            pool.add("worker01", [{"type": "cpus", "count": 4}])

    def test_add_requires_cpus(self, tmp_path):
        p = make_poolfile(tmp_path)
        pool = DistributedResourcePool(p)
        with pytest.raises(ValueError, match="cpus"):
            pool.add("worker01", [{"type": "gpus", "count": 2}])

    def test_add_with_tags_and_groups(self, tmp_path):
        p = make_poolfile(tmp_path)
        pool = DistributedResourcePool(p)
        pool.add("worker01", [{"type": "cpus", "count": 4}], tags=["gpu-node"], groups=["teamA"])
        m = pool.db["machines"][0]
        assert m["tags"] == ["gpu-node"]
        assert m["groups"] == ["teamA"]

    def test_pop_machine(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01"), machine("worker02")])
        pool = DistributedResourcePool(p)
        pool.pop("worker01")
        assert len(pool.db["machines"]) == 1
        assert pool.db["machines"][0]["hostname"] == "worker02"

    def test_pop_missing_raises(self, tmp_path):
        p = make_poolfile(tmp_path)
        pool = DistributedResourcePool(p)
        with pytest.raises(ValueError, match="Could not find"):
            pool.pop("worker99")


# ---------------------------------------------------------------------------
# DistributedResourcePool.reset / take_offline / bring_online
# ---------------------------------------------------------------------------


class TestStateManagement:
    def test_reset_restores_all_slots(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01", cpus=4)])
        pool = DistributedResourcePool(p)
        pool.checkout(req(cpus=2))
        pool.reset()
        # After reset every instance should have slots=1
        for instance in pool.db["machines"][0]["resources"]["cpus"]:
            assert instance["slots"] == 1

    def test_take_offline(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01")])
        pool = DistributedResourcePool(p)
        pool.take_offline("worker01")
        assert pool.db["machines"][0]["state"] == "offline"

    def test_take_offline_missing_raises(self, tmp_path):
        p = make_poolfile(tmp_path)
        pool = DistributedResourcePool(p)
        with pytest.raises(ValueError, match="Could not find"):
            pool.take_offline("worker99")

    def test_bring_online(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01", state="offline")])
        pool = DistributedResourcePool(p)
        pool.bring_online("worker01")
        assert pool.db["machines"][0]["state"] == "online"

    def test_bring_online_missing_raises(self, tmp_path):
        p = make_poolfile(tmp_path)
        pool = DistributedResourcePool(p)
        with pytest.raises(ValueError, match="Could not find"):
            pool.bring_online("worker99")


# ---------------------------------------------------------------------------
# DistributedResourcePool.accommodates
# ---------------------------------------------------------------------------


class TestDistributedAccommodates:
    def test_accommodates_basic(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01", cpus=4)])
        pool = DistributedResourcePool(p)
        result = pool.accommodates(req(cpus=2))
        assert result

    def test_accommodates_empty_pool(self, tmp_path):
        p = make_poolfile(tmp_path)
        pool = DistributedResourcePool(p)
        result = pool.accommodates(req(cpus=1))
        assert not result

    def test_accommodates_request_exceeds_any_machine(self, tmp_path):
        # Largest machine has 4 CPUs — requesting 8 should fail
        p = make_poolfile(tmp_path, [machine("worker01", cpus=4)])
        pool = DistributedResourcePool(p)
        result = pool.accommodates(req(cpus=8))
        assert not result

    def test_accommodates_uses_live_pool_state(self, tmp_path):
        """accommodates() must reflect current (post-checkout) availability, not initial counts.

        This is the correctness bug: the original code used resource_counts (static initial
        counts) instead of the live pool state, so it would say 'yes' even when all slots
        were checked out.
        """
        p = make_poolfile(tmp_path, [machine("worker01", cpus=4)])
        pool = DistributedResourcePool(p)
        # Check out all 4 CPUs
        pool.checkout(req(cpus=4))
        # Now accommodates should say no — all CPUs are busy
        result = pool.accommodates(req(cpus=1))
        assert not result, "accommodates must see checked-out resources as unavailable"

    def test_accommodates_offline_machine_not_counted(self, tmp_path):
        """An offline machine's resources must not satisfy accommodates."""
        p = make_poolfile(tmp_path, [machine("worker01", cpus=8, state="offline")])
        pool = DistributedResourcePool(p)
        result = pool.accommodates(req(cpus=1))
        # With the fix, offline machines are excluded; result should be False
        assert not result

    def test_accommodates_one_machine_satisfies_among_many(self, tmp_path):
        machines = [machine("small", cpus=2), machine("large", cpus=16)]
        p = make_poolfile(tmp_path, machines)
        pool = DistributedResourcePool(p)
        result = pool.accommodates(req(cpus=8))
        assert result  # large machine can satisfy it


# ---------------------------------------------------------------------------
# DistributedResourcePool.checkout
# ---------------------------------------------------------------------------


class TestDistributedCheckout:
    def test_basic_checkout(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01", cpus=4)])
        pool = DistributedResourcePool(p)
        hostname, acquired = pool.checkout(req(cpus=2))
        assert hostname == "worker01"
        assert len(acquired["cpus"]) == 2

    def test_checkout_no_machines_raises(self, tmp_path):
        p = make_poolfile(tmp_path)
        pool = DistributedResourcePool(p)
        with pytest.raises(ResourceUnavailable):
            pool.checkout(req(cpus=1))

    def test_checkout_offline_machine_skipped(self, tmp_path):
        machines = [
            machine("offline-node", cpus=8, state="offline"),
            machine("online-node", cpus=4),
        ]
        p = make_poolfile(tmp_path, machines)
        pool = DistributedResourcePool(p)
        hostname, _ = pool.checkout(req(cpus=1))
        assert hostname == "online-node"

    def test_checkout_respects_tags(self, tmp_path):
        machines = [
            machine("gpu-node", cpus=4, tags=["gpu"]),
            machine("cpu-node", cpus=4, tags=["cpu"]),
        ]
        p = make_poolfile(tmp_path, machines)
        pool = DistributedResourcePool(p)
        hostname, _ = pool.checkout(req(cpus=1), tags=["gpu"])
        assert hostname == "gpu-node"

    def test_checkout_tag_mismatch_raises(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01", cpus=4, tags=["cpu"])])
        pool = DistributedResourcePool(p)
        with pytest.raises(ResourceUnavailable):
            pool.checkout(req(cpus=1), tags=["gpu"])

    def test_checkout_respects_groups(self, tmp_path):
        machines = [
            machine("team-a-node", cpus=4, groups=["teamA"]),
            machine("team-b-node", cpus=4, groups=["teamB"]),
        ]
        p = make_poolfile(tmp_path, machines)
        pool = DistributedResourcePool(p)
        hostname, _ = pool.checkout(req(cpus=1), groups=["teamA"])
        assert hostname == "team-a-node"

    def test_checkout_multiple_requests_deplete_machine(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01", cpus=4)])
        pool = DistributedResourcePool(p)
        for _ in range(4):
            pool.checkout(req(cpus=1))
        with pytest.raises(ResourceUnavailable):
            pool.checkout(req(cpus=1))

    def test_checkout_prefers_best_fit_machine(self, tmp_path):
        """Best-fit: pick the machine that has the most remaining capacity after checkout."""
        machines = [machine("large", cpus=16), machine("small", cpus=4)]
        p = make_poolfile(tmp_path, machines)
        pool = DistributedResourcePool(p)
        # Requesting 2 CPUs — large machine will have more residual (14) vs small (2)
        hostname, _ = pool.checkout(req(cpus=2))
        assert hostname == "large"

    def test_checkout_updates_pool_state(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01", cpus=4)])
        pool = DistributedResourcePool(p)
        pool.checkout(req(cpus=2))
        # Count remaining slots in pool directly
        m = pool.db["machines"][0]
        free = sum(inst["slots"] for inst in m["resources"]["cpus"])
        assert free == 2


# ---------------------------------------------------------------------------
# DistributedResourcePool.checkin
# ---------------------------------------------------------------------------


class TestDistributedCheckin:
    def test_checkin_restores_slots(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01", cpus=4)])
        pool = DistributedResourcePool(p)
        hostname, acquired = pool.checkout(req(cpus=2))
        pool.checkin(hostname, acquired)
        m = pool.db["machines"][0]
        free = sum(inst["slots"] for inst in m["resources"]["cpus"])
        assert free == 4

    def test_checkin_unknown_host_raises(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01", cpus=4)])
        pool = DistributedResourcePool(p)
        hostname, acquired = pool.checkout(req(cpus=1))
        with pytest.raises(ValueError, match="Could not find machine"):
            pool.checkin("nonexistent", acquired)

    def test_checkout_checkin_cycle(self, tmp_path):
        p = make_poolfile(tmp_path, [machine("worker01", cpus=4)])
        pool = DistributedResourcePool(p)
        for _ in range(5):
            hostname, acquired = pool.checkout(req(cpus=2))
            pool.checkin(hostname, acquired)
            m = pool.db["machines"][0]
            free = sum(inst["slots"] for inst in m["resources"]["cpus"])
            assert free == 4
