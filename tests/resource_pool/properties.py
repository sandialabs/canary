# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import copy
import random

from _canary.resource_pool import ResourcePool
from _canary.resource_pool.rpool import NodeRequest


def request(**counts: int) -> list[NodeRequest]:
    req = NodeRequest()
    for rtype, count in counts.items():
        req.add(rtype, count)
    return [req]


def make_pool(cpus: int, gpus: int) -> ResourcePool:
    return ResourcePool(
        {
            "nodes": [
                {
                    "id": "local",
                    "resources": {
                        "cpus": [{"id": str(i), "slots": 1} for i in range(cpus)],
                        "gpus": [{"id": str(i), "slots": 1} for i in range(gpus)],
                    },
                }
            ]
        }
    )


def test_checkout_checkin_conserves_resource_pool_state():
    rng = random.Random(1234)

    for _ in range(25):
        cpus = rng.randint(1, 8)
        gpus = rng.randint(0, 4)
        pool = make_pool(cpus, gpus)

        req_cpus = rng.randint(1, cpus)
        req_gpus = rng.randint(0, gpus)

        before = copy.deepcopy(pool.getstate())

        allocation = pool.checkout(request(cpus=req_cpus, gpus=req_gpus))
        pool.checkin(allocation)

        after = pool.getstate()

        assert after == before
