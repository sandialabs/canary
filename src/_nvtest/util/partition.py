import math
from graphlib import TopologicalSorter

from .. import config
from ..test.case import TestCase
from ..util.collections import defaultlist


class Partition(set):
    @property
    def cputime(self):
        return sum(case.processors * case.runtime for case in self if not case.mask)


def group_testcases(cases: list[TestCase]) -> list[set[TestCase]]:
    """Group test cases such that a test and all its dependencies are in the
    same group

    """
    groups: list[set[TestCase]] = []
    buffer: list[set[TestCase]] = [{case} | set(case.dependencies) for case in cases]
    for temp in buffer:
        for group in groups:
            if temp & group:
                group.update(temp)
                break
        else:
            groups.append(temp)
    return sorted(filter(None, groups), key=lambda g: -len(g))


def partition_n(cases: list[TestCase], n: int = 8) -> list[set[TestCase]]:
    """Partition test cases into ``n`` partitions"""
    groups = group_testcases(cases)
    partitions = defaultlist(Partition, n)
    for group in groups:
        partition = min(partitions, key=lambda p: p.cputime)
        partition.update(group)
    return partitions


def partition_t(
    cases: list[TestCase], t: float = 60 * 30, fac: float = 1.1
) -> list[set[TestCase]]:
    """Partition test cases into partitions having a runtime approximately equal
    to ``t``

    """
    sockets_per_node = config.get("machine:sockets_per_node")
    cores_per_socket = config.get("machine:cores_per_socket")
    cores_per_node = sockets_per_node * cores_per_socket

    def _p_nodes(partition):
        max_processors = max(case.processors for case in partition)
        return math.ceil(max_processors / cores_per_node)

    partitions: list[set[TestCase]] = []
    graph = {}
    for case in cases:
        graph[case] = case.dependencies
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ready = ts.get_ready()
        groups: dict[int, list[TestCase]] = {}
        for case in ready:
            c_nodes = math.ceil(case.processors / cores_per_node)
            groups.setdefault(c_nodes, []).append(case)
        for c_nodes, group in groups.items():
            g_partitions = defaultlist(Partition)
            for case in group:
                for g_partition in g_partitions:
                    p_nodes = _p_nodes(g_partition)
                    if p_nodes != c_nodes:
                        continue
                    trial_cputime = g_partition.cputime + case.cputime
                    trial_runtime = trial_cputime / (p_nodes * cores_per_node)
                    if trial_runtime <= t / fac:
                        g_partition.add(case)
                        break
                else:
                    g_partition = g_partitions.new()
                    g_partition.add(case)
            partitions.extend(g_partitions)
        ts.done(*ready)

    if len(cases) != sum([len(partition) for partition in partitions]):
        raise ValueError("Incorrect partition lengths!")

    return partitions
