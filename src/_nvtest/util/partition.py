import math
from graphlib import TopologicalSorter
from typing import Sequence

from .. import config
from ..test.case import TestCase
from ..util.collections import defaultlist


class Partition(set):
    @property
    def cputime(self):
        return sum(case.cpus * case.runtime for case in self if not case.mask)


def groupby_dep(cases: list[TestCase]) -> list[set[TestCase]]:
    """Group cases such that a case an any of its dependencies are in the same
    group
    """
    groups: list[set[TestCase]] = []
    for case in cases:
        if case.dependencies:
            buffer = {case} | set(case.dependencies)
            for group in groups:
                if any(c in group for c in buffer):
                    group.update(buffer)
                    break
            else:
                groups.append(buffer)
    unassigned: set[TestCase] = set()
    for case in cases:
        if not case.dependencies:
            for group in groups:
                if case in group:
                    break
            else:
                unassigned.add(case)
    groups.extend([{case} for case in unassigned])
    if len(cases) != sum([len(group) for group in groups]):
        raise ValueError("Incorrect partition lengths!")
    return groups


def partition_n(cases: list[TestCase], n: int = 8) -> list[list[TestCase]]:
    """Partition test cases into ``n`` partitions"""
    partitions = defaultlist(Partition, n)
    for group in groupby_dep(cases):
        partition = min(partitions, key=lambda p: p.cputime)
        partition.update(group)
    return [p for p in partitions if len(p)]


def partition_t(
    cases: list[TestCase], t: float = 60 * 30, fac: float = 1.15
) -> list[list[TestCase]]:
    """Partition test cases into partitions having a runtime approximately equal
    to ``t``

    """
    sockets_per_node = config.get("machine:sockets_per_node")
    cores_per_socket = config.get("machine:cores_per_socket")
    cores_per_node = sockets_per_node * cores_per_socket

    partitions: list[list[TestCase]] = []

    graph = {}
    for case in cases:
        graph[case] = case.dependencies
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ready = ts.get_ready()
        groups: dict[int, list[TestCase]] = {}
        # group tests requiring the same number of nodes and attempt to create
        # partitions with equal runtimes
        for case in ready:
            c_nodes = math.ceil(case.cpus / cores_per_node)
            groups.setdefault(c_nodes, []).append(case)
        for g_nodes, group in groups.items():
            g_runtime = 0.0
            g_partition: list[TestCase] = []
            grid = tile(group, g_nodes * cores_per_node)
            assert sum(len(row) for row in grid) == len(group)
            grid_runtime = max(sum([max(c.runtime for c in row) for row in grid]), 5.0)
            target_partition_time = grid_runtime / math.ceil(grid_runtime / t)
            for row in grid:
                r_runtime = max(c.runtime for c in row)
                if r_runtime >= target_partition_time:
                    partitions.append(row)
                elif g_runtime + r_runtime <= target_partition_time:
                    g_partition.extend(row)
                    g_runtime += r_runtime
                else:
                    partitions.append(g_partition)
                    g_runtime, g_partition = r_runtime, list(row)
            if g_partition:
                partitions.append(g_partition)
        ts.done(*ready)

    if len(cases) != sum([len(partition) for partition in partitions]):
        raise ValueError("Incorrect partition lengths!")

    partitions = [p for p in partitions if p]

    return partitions


def tile(cases: Sequence[TestCase], cores: int) -> list[list[TestCase]]:
    """Tile test cases in a way that minimizes total runtime.

    Args:
      cases: Sequence of TestCase objects
      cores: the number of cores available

    The strategy employed is the First-Fit Decreasing (heuristic) bin-packing
    algorithm to create a 2D grid of test cases with dimensions cores x runtime

    1. Sort cases in decreasing runtime order
    2. Place each test case in the first row where it fits
    3. If it doesn't fit in any existing row, create a new row

    """
    grid: list[list[TestCase]] = []
    for case in sorted(cases, key=lambda c: c.runtime, reverse=True):
        for row in grid:
            row_cpus = sum(c.cpus for c in row)
            if row_cpus + case.cpus <= cores:
                row.append(case)
                break
        else:
            grid.append([case])
    return grid
