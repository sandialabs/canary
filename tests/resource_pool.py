# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import copy

import pytest

import _canary.config.schemas as schemas
import canary
from _canary.status import Status
from _canary.test.atc import AbstractTestCase
from _canary.third_party.schema import SchemaError


def test_ctest_schema():
    data = {
        "local": {
            "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
            "gpus": [{"id": "0", "slots": 1}],
        }
    }
    schemas.ctest_resource_pool_schema.validate(data)


def test_local_schema():
    data = {"resource_pool": {"cpus": 2, "gpus": 1}}
    validated = schemas.local_resource_pool_schema.validate(data)
    assert validated["resource_pool"] == {"cpus": 2, "gpus": 1}
    with pytest.raises(SchemaError):
        data = {"resource_pool": {"nodes": 1, "cpus": 2, "gpus": 1}}
        validated = schemas.local_resource_pool_schema.validate(data)
    with pytest.raises(SchemaError):
        data = {"resource_pool": {"cpus_per_node": 2, "gpus": 1}}
        validated = schemas.local_resource_pool_schema.validate(data)


def test_distributed_uniform():
    data = {"resource_pool": {"nodes": 1, "cpus_per_node": 2, "gpus_per_node": 1}}
    validated = schemas.uniform_resource_pool_schema.validate(data)
    assert validated == data
    with pytest.raises(SchemaError):
        schemas.uniform_resource_pool_schema.validate({"resource_pool": {"nodes": 1, "cpus": 2}})


def test_distributed_heterogeneous():
    data = {
        "resource_pool": [
            {
                "id": "0",
                "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
                "gpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
            },
            {
                "id": "1",
                "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
                "gpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
            },
        ]
    }
    validated = schemas.heterogeneous_resource_pool_schema.validate(data)
    assert validated == data


def test_resource_schema():
    expected = {
        "resource_pool": [
            {
                "id": "0",
                "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
                "gpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
            },
            {
                "id": "1",
                "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
                "gpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
            },
        ]
    }
    r = schemas.resource_schema
    validated = r.validate({"resource_pool": {"nodes": 2, "cpus_per_node": 2, "gpus_per_node": 2}})
    assert validated == expected
    validated = r.validate({"resource_pool": {"cpus": 2, "gpus": 2}})
    assert validated["resource_pool"][0] == expected["resource_pool"][0]
    validated = r.validate(expected)
    assert validated == expected
    data = {"local": copy.deepcopy(expected["resource_pool"][0])}
    data["local"].pop("id")
    validated = r.validate(data)
    assert validated["resource_pool"][0] == expected["resource_pool"][0]


class Case(AbstractTestCase):
    @property
    def id(self) -> str:
        return "id"

    @property
    def cpus(self) -> int:
        return 4

    @property
    def gpus(self) -> int:
        return 4

    def command(self, stage: str = "") -> list[str]:
        raise NotImplementedError

    @property
    def cputime(self) -> float:
        raise NotImplementedError

    @property
    def runtime(self) -> float:
        raise NotImplementedError

    @property
    def path(self) -> str:
        raise NotImplementedError

    def refresh(self) -> None:
        raise NotImplementedError

    def size(self) -> int:
        raise NotImplementedError

    def status(self) -> Status:
        raise NotImplementedError

    def required_resources(self) -> list[list[dict[str, object]]]:
        group: list[dict[str, object]] = []
        group.extend([{"type": "cpus", "slots": 1} for _ in range(2)])
        group.extend([{"type": "gpus", "slots": 1} for _ in range(2)])
        # by default, only one resource group is returned
        return [group]


def test_resource_pool_acquire():
    case = Case()
    with canary.config.override():
        canary.config.resource_pool.fill_uniform(node_count=1, cpus_per_node=4, gpus_per_node=4)
        resources = canary.config.resource_pool.acquire(case.required_resources())
        assert resources == [
            {
                "cpus": [{"gid": 0, "slots": 1}, {"gid": 1, "slots": 1}],
                "gpus": [{"gid": 0, "slots": 1}, {"gid": 1, "slots": 1}],
            }
        ]
        assert canary.config.resource_pool.pool == [
            {
                "id": "0",
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
        ]
