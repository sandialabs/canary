# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import math
from graphlib import TopologicalSorter
from typing import Sequence

from .. import config
from ..test.batch import TestBatch
from ..test.case import TestCase
from ..util import logging
from ..util.collections import defaultlist

size_t = tuple[int, int]


class _Partition(set):
    @property
    def cputime(self):
        return sum(case.cpus * case.runtime for case in self if not case.masked())


def groupby_dep(cases: Sequence[TestCase]) -> list[set[TestCase]]:
    """Group cases such that a case and any of its dependencies are in the same
    group
    """
    sets = [{case} | set(case.dependencies) for case in cases]
    groups: list[set[TestCase]] = []
    while sets:
        first, *rest = sets
        combined = True
        while combined:
            combined = False
            for s in rest:
                if first & s:
                    first |= s
                    s.clear()
                    combined = True
        groups.append(first)
        sets = rest
    groups = [_ for _ in groups if _]
    if len(cases) != sum([len(group) for group in groups]):
        raise ValueError("Incorrect partition lengths!")
    return groups


def partition_n(cases: Sequence[TestCase], n: int = 8) -> list[TestBatch]:
    """Partition test cases into ``n`` partitions"""
    partitions = defaultlist(_Partition, n)
    for group in groupby_dep(cases):
        partition = min(partitions, key=lambda p: p.cputime)
        partition.update(group)
    return [TestBatch(p) for p in partitions if len(p)]


def partition_x(cases: Sequence[TestCase]) -> list[TestBatch]:
    """Partition tests cases such that each partition has no intra-dependencies.  Partitions can
    depend on other partitions

    """
    graph = {}
    for case in cases:
        graph[case] = case.dependencies
    ts = TopologicalSorter(graph)
    ts.prepare()
    partitions: list[list[TestCase]] = []
    while ts.is_active():
        ready = ts.get_ready()
        partitions.append(list(ready))
        ts.done(*ready)
    return [TestBatch(p) for p in partitions if len(p)]


# modified from https://gist.github.com/shihrer/aa90d023ae0f7662919f


class Block:
    """
    Args:
      id: a string id
      width: the block width
      height: the block height

    Attributes:
      fit: Stores a Node object for output.

    """

    def __init__(self, id: str, width: int, height: int):
        self.id: str = id
        self.size: size_t = (width, height)
        self.fit: Node | None = None

    def __repr__(self):
        return f"Block({self.id}, {self.size[0]}, {self.size[1]})"

    def norm(self) -> float:
        return math.sqrt(self.size[0] ** 2 + self.size[1] ** 2)

    @property
    def width(self) -> int:
        return self.size[0]

    @width.setter
    def width(self, arg: int) -> None:
        self.size = (arg, self.height)

    @property
    def height(self) -> int:
        return self.size[1]

    @height.setter
    def height(self, arg: int) -> None:
        self.size = (self.width, arg)


class Node:
    """
    Defines an object Node for use in the packer function.  Represents the space that a block is
    placed.

    Args:
      size: The width and height of the node.
      origin: (x, y) coordinate of the top left of the node.

    Attributes:
      used: Boolean to determine if a node has been used.
      down: A node located beneath the current node.
      right: A node located to the right of the current node.
    """

    def __init__(self, origin: size_t, size: size_t):
        self.origin: size_t = origin
        self.size: size_t = size
        self.used: bool = False
        self.down: Node | None = None
        self.right: Node | None = None


class Packer:
    """Pack a list of blocks"""

    def __init__(self) -> None:
        self.root: Node | None = None
        self.auto: list[bool] = [False, False]

    def pack(
        self, blocks: list[Block], width: int | None = None, height: int | None = None
    ) -> None:
        """Initiates the packing."""
        self.auto.clear()
        self.auto.extend((False, False))
        if width is None:
            self.auto[0] = True
            width = math.ceil(1.5 * max(block.size[0] for block in blocks))
        if height is None:
            self.auto[1] = True
            height = math.ceil(1.5 * max(block.size[1] for block in blocks))
        self.root = Node((0, 0), (width, height))
        for block in blocks:
            node = self.find_node(self.root, block.size)
            if node is not None:
                block.fit = self.split_node(node, block.size)
            else:
                block.fit = self.grow_node(block.size)
        return None

    def find_node(self, node: Node, size: size_t) -> Node | None:
        if node.used:
            assert node.right is not None and node.down is not None
            return self.find_node(node.right, size) or self.find_node(node.down, size)
        elif (size[0] <= node.size[0]) and (size[1] <= node.size[1]):
            return node
        else:
            return None

    def split_node(self, node: Node, size: size_t) -> Node:
        node.used = True
        node.down = Node(
            (node.origin[0], node.origin[1] + size[1]), (node.size[0], node.size[1] - size[1])
        )
        node.right = Node(
            (node.origin[0] + size[0], node.origin[1]), (node.size[0] - size[0], size[1])
        )
        return node

    def grow_node(self, size: size_t) -> Node | None:
        assert self.root is not None
        can_go_right = self.auto[0] and size[1] <= self.root.size[1]
        can_go_down = self.auto[1] and size[0] <= self.root.size[0]

        should_go_right = can_go_right and (self.root.size[1] >= (self.root.size[0] + size[0]))
        should_go_down = can_go_down and (self.root.size[0] >= (self.root.size[1] + size[1]))

        if should_go_right:
            return self.grow_right(size)
        elif should_go_down:
            return self.grow_down(size)
        elif can_go_right:
            return self.grow_right(size)
        elif can_go_down:
            return self.grow_down(size)
        else:
            return None

    def grow_right(self, size: size_t) -> Node | None:
        assert self.root is not None
        root = Node((0, 0), (self.root.size[0] + size[0], self.root.size[1]))
        root.used = True
        root.down = self.root
        root.right = Node((self.root.size[0], 0), (size[0], self.root.size[1]))

        self.root = root

        node = self.find_node(self.root, size)
        if node is not None:
            return self.split_node(node, size)
        else:
            return None

    def grow_down(self, size: size_t) -> Node | None:
        assert self.root is not None
        root = Node((0, 0), (self.root.size[0], self.root.size[1] + size[1]))
        root.used = True
        root.down = Node((0, self.root.size[1]), (self.root.size[0], size[1]))
        root.right = self.root

        self.root = root

        node = self.find_node(self.root, size)
        if node is not None:
            return self.split_node(node, size)
        else:
            return None


def perimeter(blocks: list[Block]) -> size_t:
    max_x = max_y = 0
    for block in blocks:
        if block.fit is None:
            continue
        max_x = max(max_x, block.fit.origin[0] + block.fit.size[0])
        max_y = max(max_y, block.fit.origin[1] + block.fit.size[1])
    return max_x, max_y


def runtime(case: TestCase) -> float:
    t: float
    if case.stats is None:
        t = case.timeout
    else:
        t = (case.stats.mean + case.stats.max) / 2.0
    if t <= 5.0:
        return 5.0 * t
    elif t <= 10.0:
        return 4.0 * t
    elif t <= 30.0:
        return 3.0 * t
    elif t <= 90.0:
        return 2.0 * t
    elif t <= 300.0:
        return 2.0 * t
    return 1.25 * t


def autopartition(cases: Sequence[TestCase], t: float = 60 * 30) -> list[TestBatch]:
    logging.debug(f"Partitioning {len(cases)} test cases")
    cpus_per_node = config.resource_pool.pinfo("cpus_per_node")
    map = {case.id: case for case in cases}
    graph: dict[TestCase, list[TestCase]] = {}
    for case in cases:
        graph[case] = case.dependencies
    ts = TopologicalSorter(graph)
    ts.prepare()
    packer = Packer()
    partitions: list[TestBatch] = []
    while ts.is_active():
        ready = sorted(ts.get_ready(), key=lambda c: c.size(), reverse=True)
        blocks = [Block(case.id, case.cpus, math.ceil(runtime(case))) for case in ready]
        cpus = max(block.size[0] for block in blocks)
        nodes = math.ceil(cpus / cpus_per_node)
        width = nodes * cpus_per_node
        for i, block in enumerate(blocks):
            if ready[i].exclusive:
                block.width = width
        max_height = max(block.size[1] for block in blocks)
        height = int(max(max_height, t))
        packer.pack(blocks, width, height)
        partitions.append(TestBatch([map[b.id] for b in blocks if b.fit], runtime=float(height)))
        unfit = [block for block in blocks if not block.fit]
        while unfit:
            cpus = max(block.size[0] for block in unfit)
            nodes = math.ceil(cpus / cpus_per_node)
            width = nodes * cpus_per_node
            max_height = max(block.size[1] for block in unfit)
            height = int(max(max_height, t))
            packer.pack(unfit, width, height)
            partitions.append(TestBatch([map[b.id] for b in unfit if b.fit], runtime=float(height)))
            tmp = [block for block in unfit if not block.fit]
            if len(tmp) == len(unfit):
                raise RuntimeError("Unable to partition blocks")
            unfit = tmp
        ts.done(*ready)
    if len(cases) != sum([len(partition) for partition in partitions]):
        raise ValueError("Incorrect partition lengths!")
    logging.debug(f"Partitioned {len(cases)} test cases in to {len(partitions)} partitions")
    return [p for p in partitions if len(p)]


def packed_perimeter(cases: Sequence[TestCase]) -> size_t:
    cpus_per_node = config.resource_pool.pinfo("cpus_per_node")
    cases = sorted(cases, key=lambda c: c.size(), reverse=True)
    cpus = max(case.cpus for case in cases)
    nodes = math.ceil(cpus / cpus_per_node)
    width = nodes * cpus_per_node
    blocks = [Block(case.id, case.cpus, math.ceil(runtime(case))) for case in cases]
    for i, block in enumerate(blocks):
        if cases[i].exclusive:
            block.width = width
    packer = Packer()
    packer.pack(blocks, width=width)
    return perimeter(blocks)


def tile(cases: Sequence[TestCase], width: int) -> list[list[TestCase]]:
    """Tile test cases in a way that minimizes total runtime.

    Args:
      cases: Sequence of TestCase objects
      width: the number of cores available

    The strategy employed is the First-Fit Decreasing (heuristic) bin-packing
    algorithm to create a 2D grid of test cases with dimensions width x runtime

    1. Sort cases in decreasing runtime order
    2. Place each test case in the first row where it fits
    3. If it doesn't fit in any existing row, create a new row

    """
    grid: list[list[TestCase]] = []
    for case in sorted(cases, key=lambda c: c.size(), reverse=True):
        for row in grid:
            row_cpus = sum(c.cpus for c in row)
            if row_cpus + case.cpus <= width:
                row.append(case)
                break
        else:
            grid.append([case])
    return grid
