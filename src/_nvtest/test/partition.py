from typing import Optional
from typing import Union

from ..util import graph
from ..util.collections import defaultlist
from ..util.hash import hashit
from .testcase import TestCase


class _Partition(set):
    @property
    def cputime(self):
        return sum(case.processors * case.runtime for case in self if not case.masked)

    @property
    def runtime(self):
        return sum(case.runtime for case in self if not case.masked)

    @property
    def size(self):
        return len(self)


class Partition(list):
    """A list of test cases

    Parameters
    ----------
    world_rank:
        The index of this partition in the group
    world_size:
        The number of partitions in the group
    global_id:
        The id of the group

    """

    def __init__(
        self,
        partition: Union[list[TestCase], _Partition],
        world_rank: int,
        world_size: int,
        world_id: int = 0,
    ) -> None:
        self.world_rank = world_rank
        self.world_size = world_size
        self.world_id = world_id
        for case in partition:
            for dep in case.dependencies:
                if dep not in partition:
                    raise ValueError(f"{case}: missing dependency: {dep}")
        self.extend(graph.static_order(list(partition)))
        self.id: str = hashit("".join(_.id for _ in self), length=20)

    def ready(self) -> int:
        return 1

    @property
    def processors(self) -> int:
        return max(case.processors for case in self if not case.masked)

    @property
    def devices(self) -> int:
        return max(case.devices for case in self if not case.masked)

    @property
    def cputime(self):
        return sum(case.processors * case.runtime for case in self if not case.masked)

    @property
    def runtime(self):
        return sum(case.runtime for case in self if not case.masked)

    def run(self, log_level: Optional[int] = None) -> dict[str, dict]:
        attrs = {}
        for case in self:
            attrs[case.fullname] = case.run(log_level=log_level)
        return attrs

    def kill(self):
        for case in self:
            case.kill()


def group_testcases(cases: list[TestCase]):
    """Group test cases such that a test and all its dependencies are in the
    same group

    """
    groups: list[set[TestCase]] = [{case} | set(case.dependencies) for case in cases]
    for i, group in enumerate(groups):
        for j, other in enumerate(groups):
            if i != j and group & other:
                group.update(other)
                other.clear()
    return sorted(filter(None, groups), key=lambda g: -len(g))


def partition_n(cases: list[TestCase], n: int = 8, global_id: int = 0) -> list[Partition]:
    """Partition test cases into ``n`` partitions"""
    groups = group_testcases(cases)
    partitions = defaultlist(_Partition, n)
    for group in groups:
        partition = min(partitions, key=lambda p: p.cputime)
        partition.update(group)
    return [Partition(p, i, n, global_id) for i, p in enumerate(partitions) if p.size]


def partition_t(cases: list[TestCase], t: float = 60 * 30, global_id: int = 0) -> list[Partition]:
    """Partition test cases into partitions having a runtime approximately equal
    to ``t``

    """
    groups = group_testcases(cases)
    partitions = defaultlist(_Partition)
    for group in groups:
        runtime = sum(c.runtime for c in group)
        for partition in partitions:
            if partition.runtime + runtime <= t:
                break
        else:
            partition = partitions.new()
        partition.update(group)
    n = len(partitions)
    return [Partition(p, i, n, global_id) for i, p in enumerate(partitions)]
