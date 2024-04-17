import math
from typing import Optional
from typing import Union

from .. import config
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

    Args:
      world_rank: The index of this partition in the group
      world_size: The number of partitions in the group
      world_id: The id of the group

    """

    def __init__(
        self,
        partition: Union[list[TestCase], _Partition],
        world_rank: int,
        world_size: int,
        world_id: int = 1,
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


def group_testcases(cases: list[TestCase]) -> list[set[TestCase]]:
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


def partition_n(cases: list[TestCase], n: int = 8, world_id: int = 0) -> list[Partition]:
    """Partition test cases into ``n`` partitions"""
    groups = group_testcases(cases)
    partitions = defaultlist(_Partition, n)
    for group in groups:
        partition = min(partitions, key=lambda p: p.cputime)
        partition.update(group)
    return [Partition(p, i, n, world_id) for i, p in enumerate(partitions, start=1) if p.size]


def partition_t(cases: list[TestCase], t: float = 60 * 30, world_id: int = 1) -> list[Partition]:
    """Partition test cases into partitions having a runtime approximately equal
    to ``t``

    The partitioning is as follows:

    - Put any test requiring more than one node into its own partition
    - Fill each partition with all other

    """
    groups = group_testcases(cases)
    partitions = defaultlist(_Partition)
    sockets_per_node = config.get("machine:sockets_per_node")
    cores_per_socket = config.get("machine:cores_per_socket")
    cores_per_node = sockets_per_node * cores_per_socket

    for group in groups:
        # first pass: put all groups requiring > 1 node into their own group
        if all(case.processors <= cores_per_node for case in group):
            # only requires one node, will fill in next
            continue
        g_max_processors = max(case.processors for case in group)
        g_nodes = math.ceil(g_max_processors / cores_per_node)
        g_cputime = sum(case.cputime for case in group)
        for partition in partitions:
            p_max_processors = max(case.processors for case in partition)
            p_nodes = math.ceil(p_max_processors / cores_per_node)
            total_cputime = partition.cputime + g_cputime
            if p_nodes == g_nodes and total_cputime <= t:
                partition.update(group)
                break
        else:
            partition = partitions.new()
            partition.update(group)

    for group in groups:
        # second pass: fill in with groups requiring only 1 node
        if any(case.processors > cores_per_node for case in group):
            # requires > 1 node, already in a partition
            continue
        g_cputime = sum(case.cputime for case in group)
        for partition in partitions:
            p_max_processors = max(case.processors for case in partition)
            p_nodes = math.ceil(p_max_processors / cores_per_node)
            total_cputime = partition.cputime + g_cputime
            runtime = total_cputime / (p_nodes * cores_per_node)
            if runtime <= t:
                partition.update(group)
                break
        else:
            partition = partitions.new()
            partition.update(group)

    n = len(partitions)
    return [Partition(p, i, n, world_id) for i, p in enumerate(partitions, start=1)]
