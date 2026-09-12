# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Tests for ResourcePool (single-machine allocation primitives).

The resource model:
  - Each instance has slots=1 (one unit). add() always creates slots=1.
  - A request item {"type": "cpus", "slots": 1} = "one CPU instance".
  - To request N CPUs send N separate items: [{"type":"cpus","slots":1}] * N.
  - checkout() calls _acquire_one() once per request item, finding one instance
    with available >= requested slots.
  - Slots on an instance is treated as a binary available/busy flag in normal use.
"""

import pytest

from canary_distributed_server.rpool import EmptyResourcePoolError
from canary_distributed_server.rpool import Outcome
from canary_distributed_server.rpool import ResourcePool
from canary_distributed_server.rpool import ResourceUnavailable

# ---------------------------------------------------------------------------
# Outcome
# ---------------------------------------------------------------------------


class TestOutcome:
    def test_ok_true(self):
        o = Outcome(True)
        assert bool(o) is True
        assert o.reason is None

    def test_ok_false_requires_reason(self):
        with pytest.raises(ValueError, match="requires a reason"):
            Outcome(False)

    def test_ok_false_with_reason(self):
        o = Outcome(False, reason="not enough")
        assert bool(o) is False
        assert o.reason == "not enough"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_pool(cpus: int = 4, gpus: int = 0) -> ResourcePool:
    """Pool with N single-slot CPU instances (and optionally GPU instances)."""
    resources: dict = {"cpus": [{"id": str(i), "slots": 1} for i in range(cpus)]}
    if gpus:
        resources["gpus"] = [{"id": str(i), "slots": 1} for i in range(gpus)]
    return ResourcePool(resources)


def req(cpus: int = 1, gpus: int = 0) -> list[dict]:
    """Build a checkout request: N separate single-slot items per resource type."""
    r = [{"type": "cpus", "slots": 1} for _ in range(cpus)]
    r += [{"type": "gpus", "slots": 1} for _ in range(gpus)]
    return r


# ---------------------------------------------------------------------------
# ResourcePool.empty / types / count / slots_available
# ---------------------------------------------------------------------------


class TestResourcePoolBasics:
    def test_empty_pool(self):
        pool = ResourcePool()
        assert pool.empty() is True

    def test_nonempty_pool(self):
        pool = make_pool(cpus=2)
        assert pool.empty() is False

    def test_types(self):
        pool = make_pool(cpus=4, gpus=2)
        assert "cpus" in pool.types
        assert "gpus" in pool.types

    def test_count(self):
        pool = make_pool(cpus=3)
        assert pool.count("cpus") == 3
        assert pool.count("gpus") == 0

    def test_slots_available(self):
        pool = make_pool(cpus=4)
        assert pool.slots_available("cpus") == 4

    def test_slots_available_after_partial_checkout(self):
        pool = make_pool(cpus=4)
        pool.checkout(req(cpus=2))
        assert pool.slots_available("cpus") == 2

    def test_init_deep_copies_resources(self):
        original = {"cpus": [{"id": "0", "slots": 1}]}
        pool = ResourcePool(original)
        original["cpus"][0]["slots"] = 0
        # pool should not be affected
        assert pool.slots_available("cpus") == 1


# ---------------------------------------------------------------------------
# ResourcePool.accommodates
# ---------------------------------------------------------------------------


class TestAccommodates:
    def test_empty_pool_cannot_accommodate(self):
        pool = ResourcePool()
        result = pool.accommodates(req(cpus=1))
        assert not result
        assert "empty" in result.reason.lower()

    def test_sufficient_cpus(self):
        pool = make_pool(cpus=4)
        result = pool.accommodates(req(cpus=4))
        assert result

    def test_insufficient_cpus(self):
        pool = make_pool(cpus=2)
        result = pool.accommodates(req(cpus=3))
        assert not result
        assert "cpus" in result.reason

    def test_unknown_resource_type(self):
        pool = make_pool(cpus=4)
        result = pool.accommodates([{"type": "gpus", "slots": 1}])
        assert not result
        assert "gpus" in result.reason

    def test_multiple_resource_types(self):
        pool = make_pool(cpus=4, gpus=2)
        result = pool.accommodates(req(cpus=2, gpus=1))
        assert result

    def test_multiple_items_same_type_accumulates(self):
        pool = make_pool(cpus=3)
        # Four separate cpu items → total 4 needed, pool only has 3
        result = pool.accommodates(req(cpus=4))
        assert not result

    def test_accommodates_does_not_mutate_pool(self):
        pool = make_pool(cpus=4)
        pool.accommodates(req(cpus=4))
        assert pool.slots_available("cpus") == 4

    def test_accommodates_exact_capacity(self):
        pool = make_pool(cpus=4)
        result = pool.accommodates(req(cpus=4))
        assert result

    def test_accommodates_respects_current_availability(self):
        """accommodates must see the current (post-checkout) slot count, not the initial count."""
        pool = make_pool(cpus=4)
        pool.checkout(req(cpus=3))
        # 1 free CPU left — requesting 2 must fail
        result = pool.accommodates(req(cpus=2))
        assert not result


# ---------------------------------------------------------------------------
# ResourcePool.checkout
# ---------------------------------------------------------------------------


class TestCheckout:
    def test_basic_checkout_one_cpu(self):
        pool = make_pool(cpus=4)
        acquired = pool.checkout(req(cpus=1))
        assert "cpus" in acquired
        assert len(acquired["cpus"]) == 1
        assert pool.slots_available("cpus") == 3

    def test_basic_checkout_two_cpus(self):
        pool = make_pool(cpus=4)
        acquired = pool.checkout(req(cpus=2))
        assert len(acquired["cpus"]) == 2
        assert pool.slots_available("cpus") == 2

    def test_checkout_returns_correct_slots(self):
        pool = make_pool(cpus=4)
        acquired = pool.checkout(req(cpus=1))
        assert acquired["cpus"][0]["slots"] == 1

    def test_checkout_empty_pool_raises(self):
        pool = ResourcePool()
        with pytest.raises(EmptyResourcePoolError):
            pool.checkout(req(cpus=1))

    def test_checkout_insufficient_raises_and_rolls_back(self):
        pool = make_pool(cpus=2)
        with pytest.raises(ResourceUnavailable):
            pool.checkout(req(cpus=3))
        # pool state must be unchanged
        assert pool.slots_available("cpus") == 2

    def test_checkout_unknown_type_raises_and_rolls_back(self):
        pool = make_pool(cpus=4)
        with pytest.raises(ResourceUnavailable, match="Unknown resource type"):
            pool.checkout([{"type": "gpus", "slots": 1}])
        assert pool.slots_available("cpus") == 4

    def test_checkout_zero_slots_raises(self):
        pool = make_pool(cpus=4)
        with pytest.raises(ResourceUnavailable, match="Invalid slot request"):
            pool.checkout([{"type": "cpus", "slots": 0}])

    def test_checkout_negative_slots_raises(self):
        pool = make_pool(cpus=4)
        with pytest.raises(ResourceUnavailable, match="Invalid slot request"):
            pool.checkout([{"type": "cpus", "slots": -1}])

    def test_checkout_multiple_types(self):
        pool = make_pool(cpus=4, gpus=2)
        acquired = pool.checkout(req(cpus=2, gpus=1))
        assert "cpus" in acquired
        assert "gpus" in acquired
        assert pool.slots_available("cpus") == 2
        assert pool.slots_available("gpus") == 1

    def test_checkout_full_rollback_on_partial_failure(self):
        """First resource type succeeds, second fails → pool must be fully restored."""
        pool = make_pool(cpus=4, gpus=1)
        with pytest.raises(ResourceUnavailable):
            pool.checkout(
                [
                    {"type": "cpus", "slots": 1},
                    {"type": "gpus", "slots": 1},
                    {"type": "gpus", "slots": 1},
                ]
            )  # 2 GPUs but only 1 available
        assert pool.slots_available("cpus") == 4
        assert pool.slots_available("gpus") == 1

    def test_checkout_bin_packing_prefers_smallest_fit(self):
        """With mixed-slot instances, smallest sufficient instance is preferred."""
        resources = {"cpus": [{"id": "big", "slots": 8}, {"id": "small", "slots": 2}]}
        pool = ResourcePool(resources)
        # Requesting 1 slot — smallest instance that fits (2) should be picked
        acquired = pool.checkout([{"type": "cpus", "slots": 1}])
        assert acquired["cpus"][0]["id"] == "small"

    def test_consecutive_checkouts_deplete_pool(self):
        pool = make_pool(cpus=2)
        pool.checkout(req(cpus=1))
        pool.checkout(req(cpus=1))
        with pytest.raises(ResourceUnavailable):
            pool.checkout(req(cpus=1))

    def test_checkout_acquired_ids_are_distinct(self):
        """Two acquired CPU instances should have different IDs."""
        pool = make_pool(cpus=4)
        acquired = pool.checkout(req(cpus=2))
        ids = [item["id"] for item in acquired["cpus"]]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# ResourcePool.checkin
# ---------------------------------------------------------------------------


class TestCheckin:
    def test_checkin_restores_slots(self):
        pool = make_pool(cpus=4)
        acquired = pool.checkout(req(cpus=2))
        pool.checkin(acquired)
        assert pool.slots_available("cpus") == 4

    def test_checkin_unknown_type_raises(self):
        pool = make_pool(cpus=4)
        with pytest.raises(ValueError, match="unknown resource type"):
            pool.checkin({"gpus": [{"id": "0", "slots": 1}]})

    def test_checkin_unknown_id_raises(self):
        pool = make_pool(cpus=4)
        with pytest.raises(ValueError, match="unknown ID"):
            pool.checkin({"cpus": [{"id": "999", "slots": 1}]})

    def test_checkin_partial_restore(self):
        """Checking in 1 of 2 checked-out slots restores exactly 1."""
        pool = make_pool(cpus=4)
        acquired = pool.checkout(req(cpus=2))
        pool.checkin({"cpus": [acquired["cpus"][0]]})
        assert pool.slots_available("cpus") == 3

    def test_checkout_checkin_cycle(self):
        pool = make_pool(cpus=4)
        for _ in range(5):
            acquired = pool.checkout(req(cpus=2))
            assert pool.slots_available("cpus") == 2
            pool.checkin(acquired)
            assert pool.slots_available("cpus") == 4

    def test_double_checkin_overshoots(self):
        """Checking in the same resources twice adds slots beyond the original total.
        This is a known limitation — callers must not double-checkin."""
        pool = make_pool(cpus=2)
        acquired = pool.checkout(req(cpus=1))
        pool.checkin(acquired)
        pool.checkin(acquired)  # second checkin — slots go above original
        assert pool.slots_available("cpus") == 3  # 1 original + 2 returned
