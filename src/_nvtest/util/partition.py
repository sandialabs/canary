import math

from .. import config
from ..test.case import TestCase
from ..util.collections import defaultlist


class Partition(set):
    @property
    def cputime(self):
        return sum(case.processors * case.runtime for case in self if not case.masked)


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


def partition_n(cases: list[TestCase], n: int = 8) -> list[set[TestCase]]:
    """Partition test cases into ``n`` partitions"""
    groups = group_testcases(cases)
    partitions = defaultlist(Partition, n)
    for group in groups:
        partition = min(partitions, key=lambda p: p.cputime)
        partition.update(group)
    return partitions


def partition_t(cases: list[TestCase], t: float = 60 * 30) -> list[set[TestCase]]:
    """Partition test cases into partitions having a runtime approximately equal
    to ``t``

    The partitioning is as follows:

    - Put any test requiring more than one node into its own partition
    - Fill each partition with all other

    """
    partitions = defaultlist(Partition)
    sockets_per_node = config.get("machine:sockets_per_node")
    cores_per_socket = config.get("machine:cores_per_socket")
    cores_per_node = sockets_per_node * cores_per_socket

    def p_nodes(partition):
        max_processors = max(case.processors for case in partition)
        return math.ceil(max_processors / cores_per_node)

    unassigned: set[TestCase] = set()
    for case in cases:
        if case.dependencies:
            unassigned.add(case)
            continue
        if case.processors <= cores_per_node:
            # pack as many tests in the partition as possible
            for partition in partitions:
                nodes = p_nodes(partition)
                total_cputime = partition.cputime + 1.5 * case.cputime
                runtime = total_cputime / (nodes * cores_per_node)
                if nodes == 1 and runtime <= t:
                    partition.add(case)
                    break
            else:
                partition = partitions.new()
                partition.add(case)
        else:
            # group cases with the same number of nodes
            c_nodes = math.ceil(case.processors / cores_per_node)
            for partition in partitions:
                nodes = p_nodes(partition)
                total_cputime = partition.cputime + case.cputime
                runtime = total_cputime / (nodes * cores_per_node)
                if nodes == c_nodes and runtime <= t:
                    partition.add(case)
                    break
            else:
                partition = partitions.new()
                partition.add(case)
    for case in unassigned:
        partition = partitions.new()
        partition.add(case)
    if len(cases) != sum([len(partition) for partition in partitions]):
        raise ValueError("Incorrect partition lengths!")
    return partitions
