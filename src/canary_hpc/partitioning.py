# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import math
import statistics
from graphlib import TopologicalSorter
from typing import Any
from typing import Sequence

import psutil

import canary
from _canary.util.collections import defaultlist

from .testbatch import TestBatch

size_t = tuple[int, int]


AUTO = 1027  # automically choose batch size
ONE_PER_BATCH = 1028  # One test per batch
logger = canary.get_logger(__name__)


def partition_testcases(
    *,
    cases: list["canary.TestCase"],
    batchspec: dict[str, Any] | None = None,
    cpus_per_node: int | None = None,
) -> list["TestBatch"]:
    cpus_per_node = cpus_per_node or psutil.cpu_count(logical=True)
    batchspec = batchspec or {"nodes": "any", "layout": "flat", "count": None, "duration": 30 * 60}
    nodes = batchspec["nodes"] or "any"
    layout = batchspec["layout"] or "flat"
    if batchspec["duration"] is not None:
        duration = float(batchspec["duration"])  # 30 minute default
        logger.debug(f"Batching test cases using duration={duration}")
        return partition_t(cases, t=duration, nodes=nodes, cpus_per_node=cpus_per_node)
    else:
        assert batchspec["count"] is not None
        count = int(batchspec["count"])
        logger.debug(f"Batching test cases using count={count}")
        if layout == "atomic":
            return partition_n_atomic(cases, n=count)
        return partition_n(cases, n=count, nodes=nodes)


def partition_n_atomic(cases: Sequence[canary.TestCase], n: int = 8) -> list["TestBatch"]:
    """Partition tests cases into ``n`` "atomic" partitions such that each partition is independent
    of any other partition.  This applies that each partition may have test cases dependent on other
    cases in the partition (intra-partition dependencies).

    A note on the value of ``n``:

    * If ``n == ONE_PER_BATCH``, tests are put into individual batches
    * If ``n == AUTO``, tests are put into batches automatically
    * If ``n >= 1``, tests are put into *at most* ``n`` batches, though it may be less.

    """
    if n <= 0:
        raise ValueError(f"Cannot create atomic batches with count {n=}")
    if n == ONE_PER_BATCH:
        raise ValueError("Cannot create atomic batches with one test per batch")
    if n == 1:
        return [TestBatch(cases)]
    groups = groupby_dep(cases)
    if n == AUTO:
        batches: list[TestBatch] = [TestBatch(list(group)) for group in groups if len(group) > 1]
        mean_batch_length = statistics.mean([b.size() for b in batches])
        p: _Partition = _Partition()
        for group in groups:
            if len(group) == 1:
                p.update(group)
                if p.size() >= mean_batch_length:
                    batches.append(TestBatch(list(p)))
                    p.clear()
        if p:
            batches.append(TestBatch(list(p)))
        return batches
    else:
        partitions = defaultlist(_Partition, n)
        for group in groups:
            partition = min(partitions, key=lambda p: p.size())
            partition.update(group)
        return [TestBatch(p) for p in partitions if len(p)]


def partition_n(
    cases: Sequence[canary.TestCase], n: int = 8, nodes: str = "any"
) -> list["TestBatch"]:
    """Partition tests cases into ``n`` partitions such that each partition has no
    intra-dependencies.  Partitions can depend on other partitions.

    A note on the value of ``n``:

    * If ``n == ONE_PER_BATCH``, tests are put into individual batches
    * If ``n == AUTO``, tests are batched such that each batch contains no inter-batch dependencies
    * If ``n >= 1``, tests are put into *at most* ``n`` batches, though it may be less.

    """
    assert nodes in ("any", "same")
    if n == ONE_PER_BATCH:
        return [TestBatch([case]) for case in cases]
    elif n == 1:
        return [TestBatch(cases)]
    graph = {}
    for case in cases:
        graph[case] = [dep for dep in case.dependencies if dep in cases]
    ts = TopologicalSorter(graph)
    ts.prepare()
    sizes: list[float] = []
    groups: list[list[canary.TestCase]] = []
    while ts.is_active():
        ready = ts.get_ready()
        if nodes == "same":
            node_groups: dict[int, list[canary.TestCase]] = {}
            for case in ready:
                node_groups.setdefault(nodes_required(case), []).append(case)
            groups.extend(node_groups.values())
        else:
            groups.append(list(ready))
        sizes.append(sum(c.size() for c in groups[-1] if not c.wont_run()))
        ts.done(*ready)
    if n == AUTO:
        return [TestBatch(list(group)) for group in groups]
    if len(groups) > n:
        raise ValueError(f"At least {len(groups)} required to partition test cases")
    # determine the number of batches each partition will receive
    total_size = sum(sizes)
    ix = sorted(range(len(groups)), key=lambda i: sizes[i])
    groups = [groups[i] for i in ix]
    sizes = [sizes[i] for i in ix]
    nbatches_each = [max(1, math.floor(n * t / total_size)) for t in sizes[:-1]]
    nbatches_each.append(n - sum(nbatches_each))
    batches: list[TestBatch] = []
    for i, group in enumerate(groups):
        ps = defaultlist(_Partition, nbatches_each[i])
        for case in group:
            p = min(ps, key=lambda p: p.size())
            p.add(case)
        batches.extend([TestBatch(p) for p in ps if len(p)])
    return batches


def partition_t(
    cases: Sequence[canary.TestCase],
    t: float = 60 * 30,
    nodes: str = "any",
    cpus_per_node: int | None = None,
) -> list[TestBatch]:
    """Partition test cases by tiling them in the 2D space defined by num_cpus x run_time"""
    logger.debug(f"Partitioning {len(cases)} test cases")

    cpus_per_node = cpus_per_node or psutil.cpu_count(logical=True)
    assert isinstance(cpus_per_node, int)

    def _pack_ready_nodes(
        packer: "Packer", batches: list[TestBatch], ready: list[canary.TestCase], cpus_per_node: int
    ):
        blocks = [Block(case.id, case.cpus, math.ceil(runtime(case))) for case in ready]
        cpus = max(block.size[0] for block in blocks)
        nodes_reqd = math.ceil(cpus / cpus_per_node)
        width = nodes_reqd * cpus_per_node
        for i, block in enumerate(blocks):
            if ready[i].exclusive:
                block.width = width
        max_height = max(block.size[1] for block in blocks)
        height = int(max(max_height, t))
        packer.pack(blocks, width, height)
        batches.append(TestBatch([map[b.id] for b in blocks if b.fit], runtime=float(height)))
        unfit = [block for block in blocks if not block.fit]
        while unfit:
            cpus = max(block.size[0] for block in unfit)
            nodes_reqd = math.ceil(cpus / cpus_per_node)
            width = nodes_reqd * cpus_per_node
            max_height = max(block.size[1] for block in unfit)
            height = int(max(max_height, t))
            packer.pack(unfit, width, height)
            batches.append(TestBatch([map[b.id] for b in unfit if b.fit], runtime=float(height)))
            tmp = [block for block in unfit if not block.fit]
            if len(tmp) == len(unfit):
                raise RuntimeError("Unable to partition blocks")
            unfit = tmp

    map: dict[str, canary.TestCase] = {case.id: case for case in cases}
    graph: dict[canary.TestCase, list[canary.TestCase]] = {}
    for case in cases:
        graph[case] = [dep for dep in case.dependencies if dep in cases]
    ts = TopologicalSorter(graph)
    ts.prepare()
    packer = Packer()
    batches: list[TestBatch] = []
    while ts.is_active():
        ready = sorted(ts.get_ready(), key=lambda c: c.size(), reverse=True)
        if nodes == "same":
            node_groups: dict[int, list[canary.TestCase]] = {}
            for case in ready:
                node_groups.setdefault(nodes_required(case), []).append(case)
            for group in node_groups.values():
                _pack_ready_nodes(packer, batches, group, cpus_per_node)
        else:
            _pack_ready_nodes(packer, batches, ready, cpus_per_node)
        ts.done(*ready)
    if len(cases) != sum([len(b) for b in batches]):
        raise ValueError("Incorrect partition lengths!")
    logger.debug(f"Partitioned {len(cases)} test cases in to {len(batches)} batches")
    return [b for b in batches if len(b)]


def nodes_required(case: canary.TestCase) -> int:
    return case.nodes


class _Partition(set):
    def size(self):
        vector = [0.0, 0.0, 0.0]
        for case in self:
            if not case.wont_run():
                vector[0] += case.cpus
                vector[1] += case.gpus
                vector[2] += case.runtime
        return math.sqrt(sum(x**2 for x in vector))


def groupby_dep(cases: Sequence[canary.TestCase]) -> list[set[canary.TestCase]]:
    """Group cases such that a case and any of its dependencies are in the same
    group
    """
    sets = [{case} | set(case.dependencies) for case in cases]
    groups: list[set[canary.TestCase]] = []
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


def runtime(case: canary.TestCase) -> float:
    t = case.runtime
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


def packed_perimeter(cases: Sequence[canary.TestCase], cpus_per_node: int | None = None) -> size_t:
    cpus_per_node = cpus_per_node or psutil.cpu_count(logical=True)
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


def tile(cases: Sequence[canary.TestCase], width: int) -> list[list[canary.TestCase]]:
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
    grid: list[list[canary.TestCase]] = []
    for case in sorted(cases, key=lambda c: c.size(), reverse=True):
        for row in grid:
            row_cpus = sum(c.cpus for c in row)
            if row_cpus + case.cpus <= width:
                row.append(case)
                break
        else:
            grid.append([case])
    return grid
