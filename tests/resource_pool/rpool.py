# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import pytest
from schema import SchemaError

import _canary.resource_pool.schemas as schemas
from _canary.resource_pool import ResourcePool
from _canary.resource_pool.rpool import EmptyResourcePoolError
from _canary.resource_pool.rpool import ResourceUnavailable


def test_schema_rejects_flat_resource_pool_shorthand():
    data = {"cpus": 2, "gpus": 1}

    with pytest.raises(SchemaError):
        schemas.resource_pool_schema.validate(data)


def test_schema_accepts_explicit_nodes():
    data = {
        "additional_properties": {},
        "nodes": [
            {
                "id": "0",
                "resources": {
                    "cpus": [{"id": "0", "slots": 1}],
                    "gpus": [{"id": "0", "slots": 1}],
                },
            },
            {
                "id": "1",
                "resources": {
                    "cpus": [{"id": "0", "slots": 1}],
                    "gpus": [{"id": "0", "slots": 1}],
                },
            },
        ],
    }

    validated = schemas.resource_pool_schema.validate(data)

    assert validated["additional_properties"] == {}
    assert validated["nodes"][0]["id"] == "0"
    assert validated["nodes"][0]["state"] == "online"
    assert validated["nodes"][0]["tags"] == []
    assert validated["nodes"][0]["groups"] == []
    assert validated["nodes"][0]["additional_properties"] == {}
    assert validated["nodes"][1]["id"] == "1"


def test_resource_populate_single_node():
    rp = ResourcePool()
    rp.populate(cpus=1, gpus=1)

    state = rp.getstate()
    assert state == {
        "additional_properties": {},
        "nodes": [
            {
                "id": os.uname().nodename,
                "resources": {
                    "cpus": [{"id": "0", "slots": 1}],
                    "gpus": [{"id": "0", "slots": 1}],
                },
            }
        ],
    }

    assert rp.count("nodes") == 1
    assert rp.count("cpus") == 1
    assert rp.count("gpus") == 1
    assert rp.count_per_node("cpus") == 1
    assert rp.count_per_node("gpus") == 1


def test_resource_populate_single_node_no_gpus():
    rp = ResourcePool()
    rp.populate(cpus=1, gpus=0)

    state = rp.getstate()
    assert state["nodes"][0]["resources"] == {
        "cpus": [{"id": "0", "slots": 1}],
        "gpus": [],
    }

    assert rp.count("nodes") == 1
    assert rp.count("cpus") == 1
    assert rp.count("gpus") == 0
    assert rp.count_per_node("cpus") == 1
    assert rp.count_per_node("gpus") == 0


def test_single_node_accommodates():
    rp = ResourcePool(
        {
            "nodes": [
                {
                    "id": "local",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
                        "gpus": [{"id": "0", "slots": 1}],
                    },
                }
            ]
        }
    )

    assert rp.accommodates([{"type": "cpus", "slots": 2}, {"type": "gpus", "slots": 1}])

    assert not rp.accommodates([{"type": "cpus", "slots": 3}, {"type": "gpus", "slots": 1}])

    assert not rp.accommodates([{"type": "cpus", "slots": 1}, {"type": "gpus", "slots": 2}])


def test_single_node_checkout_and_checkin():
    rp = ResourcePool(
        {
            "additional_properties": {"baz": "spam"},
            "nodes": [
                {
                    "id": "local",
                    "resources": {
                        "cpus": [
                            {"id": "0", "slots": 1},
                            {"id": "1", "slots": 1},
                            {"id": "2", "slots": 1},
                            {"id": "3", "slots": 1},
                        ],
                        "gpus": [
                            {"id": "0", "slots": 1},
                            {"id": "1", "slots": 1},
                            {"id": "2", "slots": 1},
                            {"id": "3", "slots": 1},
                        ],
                    },
                }
            ],
        }
    )

    request = [
        {"type": "cpus", "slots": 1},
        {"type": "cpus", "slots": 1},
        {"type": "gpus", "slots": 1},
        {"type": "gpus", "slots": 1},
    ]

    acquired = rp.checkout(request)

    assert acquired == {
        "cpus": [
            {"node": "local", "id": "0", "slots": 1},
            {"node": "local", "id": "1", "slots": 1},
        ],
        "gpus": [
            {"node": "local", "id": "0", "slots": 1},
            {"node": "local", "id": "1", "slots": 1},
        ],
    }

    assert rp.getstate()["nodes"][0]["resources"] == {
        "cpus": [
            {"id": "0", "slots": 0},
            {"id": "1", "slots": 0},
            {"id": "2", "slots": 1},
            {"id": "3", "slots": 1},
        ],
        "gpus": [
            {"id": "0", "slots": 0},
            {"id": "1", "slots": 0},
            {"id": "2", "slots": 1},
            {"id": "3", "slots": 1},
        ],
    }

    rp.checkin(acquired)

    assert rp.getstate()["nodes"][0]["resources"] == {
        "cpus": [
            {"id": "0", "slots": 1},
            {"id": "1", "slots": 1},
            {"id": "2", "slots": 1},
            {"id": "3", "slots": 1},
        ],
        "gpus": [
            {"id": "0", "slots": 1},
            {"id": "1", "slots": 1},
            {"id": "2", "slots": 1},
            {"id": "3", "slots": 1},
        ],
    }


def test_single_node_checkout_uses_node_local_resource_ids():
    rp = ResourcePool(
        {
            "nodes": [
                {
                    "id": "local",
                    "resources": {
                        "cpus": [{"id": "01", "slots": 2}, {"id": "ab", "slots": 3}],
                        "gpus": [{"id": "02", "slots": 3}, {"id": "cd", "slots": 5}],
                    },
                }
            ]
        }
    )

    acquired = rp.checkout([{"type": "cpus", "slots": 1}, {"type": "gpus", "slots": 1}])

    assert acquired == {
        "cpus": [{"node": "local", "id": "01", "slots": 1}],
        "gpus": [{"node": "local", "id": "02", "slots": 1}],
    }

    rp.checkin(acquired)

    acquired = rp.checkout([{"type": "cpus", "slots": 3}, {"type": "gpus", "slots": 3}])

    assert acquired == {
        "cpus": [{"node": "local", "id": "ab", "slots": 3}],
        "gpus": [{"node": "local", "id": "02", "slots": 3}],
    }


def test_single_node_checkout_requires_colocation():
    rp = ResourcePool(
        {
            "nodes": [
                {
                    "id": "cpu-node",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 4}],
                        "gpus": [],
                    },
                },
                {
                    "id": "gpu-node",
                    "resources": {
                        "cpus": [],
                        "gpus": [{"id": "0", "slots": 1}],
                    },
                },
            ]
        }
    )

    request = [{"type": "cpus", "slots": 1}, {"type": "gpus", "slots": 1}]

    assert not rp.accommodates(request)

    with pytest.raises(ResourceUnavailable):
        rp.checkout(request)


def test_single_node_checkout_skips_offline_nodes():
    rp = ResourcePool(
        {
            "nodes": [
                {
                    "id": "offline-node",
                    "state": "offline",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 4}],
                    },
                },
                {
                    "id": "online-node",
                    "state": "online",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 4}],
                    },
                },
            ]
        }
    )

    acquired = rp.checkout([{"type": "cpus", "slots": 1}])

    assert acquired == {
        "cpus": [{"node": "online-node", "id": "0", "slots": 1}],
    }


def test_checkout_with_tags_and_groups():
    rp = ResourcePool(
        {
            "nodes": [
                {
                    "id": "default-node",
                    "tags": ["cpu"],
                    "groups": ["default"],
                    "resources": {
                        "cpus": [{"id": "0", "slots": 4}],
                    },
                },
                {
                    "id": "gpu-node",
                    "tags": ["gpu"],
                    "groups": ["nightly"],
                    "resources": {
                        "cpus": [{"id": "0", "slots": 4}],
                    },
                },
            ]
        }
    )

    acquired = rp.checkout([{"type": "cpus", "slots": 1}], tags=["gpu"])
    assert acquired == {
        "cpus": [{"node": "gpu-node", "id": "0", "slots": 1}],
    }

    rp.checkin(acquired)

    acquired = rp.checkout([{"type": "cpus", "slots": 1}], groups=["nightly"])
    assert acquired == {
        "cpus": [{"node": "gpu-node", "id": "0", "slots": 1}],
    }


def test_multi_node_request_requires_allow_multi_node():
    rp = ResourcePool(
        {
            "additional_properties": {},
            "nodes": [
                {
                    "id": "0",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 2}],
                    },
                },
                {
                    "id": "1",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 2}],
                    },
                },
            ],
        },
        allow_multi_node=False,
    )

    request = [{"type": "nodes", "slots": 2}, {"type": "cpus", "slots": 1}]

    assert not rp.accommodates(request)

    with pytest.raises(ResourceUnavailable):
        rp.checkout(request)


def test_multi_node_accommodates():
    rp = ResourcePool(
        {
            "additional_properties": {},
            "nodes": [
                {
                    "id": "0",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 2}],
                        "gpus": [{"id": "0", "slots": 1}],
                    },
                },
                {
                    "id": "1",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 2}],
                        "gpus": [{"id": "0", "slots": 1}],
                    },
                },
            ],
        },
        allow_multi_node=True,
    )

    assert rp.accommodates(
        [
            {"type": "nodes", "slots": 2},
            {"type": "cpus", "slots": 1},
            {"type": "gpus", "slots": 1},
        ]
    )

    assert not rp.accommodates(
        [
            {"type": "nodes", "slots": 3},
            {"type": "cpus", "slots": 1},
            {"type": "gpus", "slots": 1},
        ]
    )

    assert not rp.accommodates(
        [
            {"type": "nodes", "slots": 2},
            {"type": "cpus", "slots": 1},
            {"type": "gpus", "slots": 2},
        ]
    )


def test_multi_node_checkout_and_checkin():
    rp = ResourcePool(
        {
            "additional_properties": {},
            "nodes": [
                {
                    "id": "0",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 2}, {"id": "1", "slots": 2}],
                        "gpus": [{"id": "0", "slots": 1}],
                    },
                },
                {
                    "id": "1",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 2}, {"id": "1", "slots": 2}],
                        "gpus": [{"id": "0", "slots": 1}],
                    },
                },
            ],
        },
        allow_multi_node=True,
    )

    request = [
        {"type": "nodes", "slots": 2},
        {"type": "cpus", "slots": 1},
        {"type": "gpus", "slots": 1},
    ]

    acquired = rp.checkout(request)

    assert acquired == {
        "cpus": [
            {"node": "0", "id": "0", "slots": 1},
            {"node": "1", "id": "0", "slots": 1},
        ],
        "gpus": [
            {"node": "0", "id": "0", "slots": 1},
            {"node": "1", "id": "0", "slots": 1},
        ],
    }

    assert rp.get_node("0").resources == {
        "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 2}],
        "gpus": [{"id": "0", "slots": 0}],
    }
    assert rp.get_node("1").resources == {
        "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 2}],
        "gpus": [{"id": "0", "slots": 0}],
    }

    rp.checkin(acquired)

    assert rp.get_node("0").resources == {
        "cpus": [{"id": "0", "slots": 2}, {"id": "1", "slots": 2}],
        "gpus": [{"id": "0", "slots": 1}],
    }
    assert rp.get_node("1").resources == {
        "cpus": [{"id": "0", "slots": 2}, {"id": "1", "slots": 2}],
        "gpus": [{"id": "0", "slots": 1}],
    }


def test_multi_node_request_is_per_node():
    rp = ResourcePool(
        {
            "additional_properties": {},
            "nodes": [
                {
                    "id": "0",
                    "resources": {
                        "gpus": [{"id": "0", "slots": 1}],
                    },
                },
                {
                    "id": "1",
                    "resources": {
                        "gpus": [{"id": "0", "slots": 1}],
                    },
                },
            ],
        },
        allow_multi_node=True,
    )

    acquired = rp.checkout([{"type": "nodes", "slots": 2}, {"type": "gpus", "slots": 1}])

    assert acquired == {
        "gpus": [
            {"node": "0", "id": "0", "slots": 1},
            {"node": "1", "id": "0", "slots": 1},
        ]
    }

    assert not rp.accommodates([{"type": "nodes", "slots": 2}, {"type": "gpus", "slots": 1}])


def test_count_and_slots_by_node():
    rp = ResourcePool(
        {
            "additional_properties": {},
            "nodes": [
                {
                    "id": "0",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 2}, {"id": "1", "slots": 2}],
                        "gpus": [{"id": "0", "slots": 1}],
                    },
                },
                {
                    "id": "1",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 2}, {"id": "1", "slots": 2}],
                        "gpus": [{"id": "0", "slots": 1}],
                    },
                },
            ],
        },
        allow_multi_node=True,
    )

    assert rp.count("nodes") == 2
    assert rp.count("cpus") == 4
    assert rp.count("gpus") == 2

    assert rp.count_by_node("cpus") == {"0": 2, "1": 2}
    assert rp.count_by_node("gpus") == {"0": 1, "1": 1}

    assert rp.slots_by_node("cpus") == {"0": 4, "1": 4}
    assert rp.slots_by_node("gpus") == {"0": 1, "1": 1}

    assert rp.count_per_node("cpus") == 2
    assert rp.count_per_node("gpus") == 1


def test_count_per_node_raises_for_heterogeneous_pool():
    rp = ResourcePool(
        {
            "nodes": [
                {
                    "id": "0",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
                    },
                },
                {
                    "id": "1",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 1}],
                    },
                },
            ]
        }
    )

    with pytest.raises(ResourceUnavailable):
        rp.count_per_node("cpus")


def test_checkin_requires_node_field():
    rp = ResourcePool(
        {
            "nodes": [
                {
                    "id": "local",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 1}],
                    },
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="missing node"):
        rp.checkin({"cpus": [{"id": "0", "slots": 1}]})


def test_checkin_rejects_unknown_node():
    rp = ResourcePool(
        {
            "nodes": [
                {
                    "id": "local",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 1}],
                    },
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="unknown node"):
        rp.checkin({"cpus": [{"node": "missing", "id": "0", "slots": 1}]})


def test_empty_resource_pool_errors():
    rp = ResourcePool()

    with pytest.raises(EmptyResourcePoolError):
        rp.accommodates([{"type": "cpus", "slots": 1}])

    with pytest.raises(EmptyResourcePoolError):
        rp.checkout([{"type": "cpus", "slots": 1}])
