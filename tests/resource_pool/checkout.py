# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import copy
import random
from typing import Any

import pytest

from _canary.resource_pool import ResourcePool
from _canary.resource_pool.rpool import NodeRequest
from _canary.resource_pool.rpool import ResourceUnavailable


def counted_node_request(*, exclusive: bool = False, **counts: int) -> list[NodeRequest]:
    req = NodeRequest()
    req.exclusive = exclusive
    for rtype, count in counts.items():
        req.add(rtype, count)
    return [req]


def make_single_node_pool(*, cpus: int = 4, gpus: int = 2) -> ResourcePool:
    return ResourcePool(
        {
            "additional_properties": {},
            "nodes": [
                {
                    "id": "local",
                    "resources": {
                        "cpus": [{"id": str(i), "slots": 1} for i in range(cpus)],
                        "gpus": [{"id": str(i), "slots": 1} for i in range(gpus)],
                    },
                }
            ],
        }
    )


def test_failed_checkout_does_not_mutate_pool_state() -> None:
    pool = make_single_node_pool(cpus=4, gpus=1)
    before = copy.deepcopy(pool.getstate())

    with pytest.raises(ResourceUnavailable):
        pool.checkout(counted_node_request(cpus=2, gpus=2))

    after = pool.getstate()
    assert after == before


def test_checkout_checkin_roundtrip_restores_exact_state() -> None:
    pool = make_single_node_pool(cpus=4, gpus=2)
    before = copy.deepcopy(pool.getstate())

    allocation = pool.checkout(counted_node_request(cpus=2, gpus=1))
    pool.checkin(allocation)

    assert pool.getstate() == before


def test_repeated_checkout_checkin_roundtrip_restores_exact_state() -> None:
    pool = make_single_node_pool(cpus=8, gpus=4)
    before = copy.deepcopy(pool.getstate())

    for _ in range(10):
        allocation = pool.checkout(counted_node_request(cpus=3, gpus=2))
        pool.checkin(allocation)

    assert pool.getstate() == before


def test_checkin_rejects_unknown_resource_type_without_mutation() -> None:
    pool = make_single_node_pool(cpus=2, gpus=0)
    before = copy.deepcopy(pool.getstate())

    bad_allocation = {
        "metadata": {},
        "resources": {"licenses": [{"node": "local", "id": "0", "slots": 1}]},
    }

    with pytest.raises((ValueError, ResourceUnavailable, KeyError)):
        pool.checkin(bad_allocation)

    assert pool.getstate() == before


def test_checkin_rejects_unknown_resource_id_without_mutation() -> None:
    pool = make_single_node_pool(cpus=2, gpus=0)
    before = copy.deepcopy(pool.getstate())

    bad_allocation = {
        "metadata": {},
        "resources": {"cpus": [{"node": "local", "id": "missing", "slots": 1}]},
    }

    with pytest.raises((ValueError, ResourceUnavailable, KeyError)):
        pool.checkin(bad_allocation)

    assert pool.getstate() == before


def test_checkin_rejects_nonpositive_slots_without_mutation() -> None:
    pool = make_single_node_pool(cpus=2, gpus=0)
    before = copy.deepcopy(pool.getstate())

    bad_allocation = {
        "metadata": {},
        "resources": {"cpus": [{"node": "local", "id": "0", "slots": 0}]},
    }

    with pytest.raises((ValueError, ResourceUnavailable)):
        pool.checkin(bad_allocation)

    assert pool.getstate() == before


def test_checkin_rejects_partial_invalid_allocation_atomically() -> None:
    pool = make_single_node_pool(cpus=2, gpus=0)

    allocation = pool.checkout(counted_node_request(cpus=1))
    checked_out_state = copy.deepcopy(pool.getstate())

    # Mix one valid return with one invalid return. The valid part must not
    # be applied if the overall checkin is invalid.
    bad_allocation = copy.deepcopy(allocation)
    bad_allocation["resources"]["cpus"].append({"node": "local", "id": "missing", "slots": 1})

    with pytest.raises((ValueError, ResourceUnavailable, KeyError)):
        pool.checkin(bad_allocation)

    assert pool.getstate() == checked_out_state


def test_double_checkin_does_not_overfill_pool() -> None:
    pool = make_single_node_pool(cpus=2, gpus=0)
    before = copy.deepcopy(pool.getstate())

    allocation = pool.checkout(counted_node_request(cpus=1))
    pool.checkin(allocation)

    assert pool.getstate() == before

    # Desired hardened behavior: a second checkin of the same allocation should
    # not increase available slots beyond original capacity.
    with pytest.raises((ValueError, ResourceUnavailable)):
        pool.checkin(allocation)

    assert pool.getstate() == before


def test_randomized_checkout_checkin_conserves_pool_state() -> None:
    rng = random.Random(12345)

    for _ in range(50):
        cpus = rng.randint(1, 12)
        gpus = rng.randint(0, 6)

        pool = make_single_node_pool(cpus=cpus, gpus=gpus)
        before = copy.deepcopy(pool.getstate())

        req_cpus = rng.randint(1, cpus)
        req_gpus = rng.randint(0, gpus)

        allocation = pool.checkout(counted_node_request(cpus=req_cpus, gpus=req_gpus))
        pool.checkin(allocation)

        assert pool.getstate() == before


def test_checkout_all_resources_then_rejects_second_checkout() -> None:
    pool = make_single_node_pool(cpus=2, gpus=1)

    allocation = pool.checkout(counted_node_request(cpus=2, gpus=1))

    with pytest.raises(ResourceUnavailable):
        pool.checkout(counted_node_request(cpus=1))

    pool.checkin(allocation)

    assert pool.accommodates(counted_node_request(cpus=2, gpus=1))


def test_checkin_requires_resources_mapping() -> None:
    pool = make_single_node_pool(cpus=1, gpus=0)
    before = copy.deepcopy(pool.getstate())

    with pytest.raises((ValueError, KeyError, TypeError)):
        pool.checkin({"metadata": {}})

    assert pool.getstate() == before


def test_checkin_rejects_malformed_resource_entries_without_mutation() -> None:
    pool = make_single_node_pool(cpus=1, gpus=0)
    before = copy.deepcopy(pool.getstate())

    malformed_cases: list[dict[str, Any]] = [
        {"resources": {"cpus": [{"id": "0", "slots": 1}]}},  # missing node
        {"resources": {"cpus": [{"node": "local", "slots": 1}]}},  # missing id
        {"resources": {"cpus": [{"node": "local", "id": "0"}]}},  # missing slots
        {"resources": {"cpus": [{"node": "local", "id": "0", "slots": "one"}]}},
    ]

    for allocation in malformed_cases:
        with pytest.raises((ValueError, KeyError, TypeError)):
            pool.checkin(allocation)
        assert pool.getstate() == before
