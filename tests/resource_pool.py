# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


import _canary.config.schemas as schemas
from _canary.atc import AbstractTestCase
from _canary.resource_pool import ResourcePool
from _canary.status import Status


def test_fill_simple():
    data = {"cpus": 2, "gpus": 1}
    validated = schemas.resource_pool_schema.validate(data)
    assert validated["resources"] == {
        "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
        "gpus": [{"id": "0", "slots": 1}],
    }


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

    @property
    def working_directory(self) -> str:
        raise NotImplementedError

    def refresh(self) -> None:
        raise NotImplementedError

    def reload_and_check(self) -> None:
        raise NotImplementedError

    def run(self) -> None:
        raise NotImplementedError

    def save(self) -> None:
        raise NotImplementedError

    def finish(self) -> None:
        raise NotImplementedError

    @property
    def duration(self) -> float:
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


def test_resource_pool_checkout():
    case = Case()
    pool = ResourcePool()
    pool.populate(cpus=4, gpus=4)
    resources = pool.checkout(case.required_resources())
    expected = [
        {
            "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
            "gpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
        }
    ]
    assert resources == expected
    assert pool.resources == {
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


def test_resource_populate():
    rp = ResourcePool()
    rp.populate(cpus=1, gpus=1)
    assert rp.resources == {
        "cpus": [{"id": "0", "slots": 1}],
        "gpus": [{"id": "0", "slots": 1}],
    }


def test_resource_pool_modify():
    rp = ResourcePool()
    rp.populate(cpus=1)
    assert rp.resources == {"cpus": [{"id": "0", "slots": 1}]}
    rp.modify(gpus=1)
    assert rp.resources == {
        "cpus": [{"id": "0", "slots": 1}],
        "gpus": [{"id": "0", "slots": 1}],
    }


def test_resource_pool_fill():
    rp = ResourcePool()
    pool = {
        "additional_properties": {"baz": "spam"},
        "resources": {
            "cpus": [{"id": "01", "slots": 2}, {"id": "ab", "slots": 3}],
            "gpus": [{"id": "02", "slots": 4}, {"id": "cd", "slots": 3}],
        },
    }
    rp.fill(pool)


def test_resource_checkout():
    rp = ResourcePool()
    pool = {
        "additional_properties": {"baz": "spam"},
        "resources": {
            "cpus": [{"id": "01", "slots": 2}, {"id": "ab", "slots": 3}],
            "gpus": [{"id": "02", "slots": 3}, {"id": "cd", "slots": 5}],
        },
    }
    rp.fill(pool)
    x = rp.checkout([[{"type": "cpus", "slots": 1}, {"type": "gpus", "slots": 1}]])
    assert x == [{"cpus": [{"id": "01", "slots": 1}], "gpus": [{"id": "02", "slots": 1}]}]
    rp.checkin(x)
    x = rp.checkout([[{"type": "cpus", "slots": 3}, {"type": "gpus", "slots": 3}]])
    assert x == [{"cpus": [{"id": "ab", "slots": 3}], "gpus": [{"id": "02", "slots": 3}]}]
