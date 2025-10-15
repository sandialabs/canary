# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import math
from graphlib import TopologicalSorter
from typing import Any
from typing import Iterable

import psutil

import canary

from .partitioning import Block
from .partitioning import Bucket
from .partitioning import Packer
from .partitioning import pack_by_count
from .partitioning import pack_by_count_atomic
from .partitioning import pack_to_height
from .partitioning import perimeter
from .testbatch import TestBatch

logger = canary.get_logger(__name__)


def batch_testcases(
    *,
    cases: list["canary.TestCase"],
    batchspec: dict[str, Any] | None = None,
    cpus_per_node: int | None = None,
) -> list["TestBatch"]:
    cpus_per_node = cpus_per_node or psutil.cpu_count()
    batchspec = batchspec or {"nodes": "any", "layout": "flat", "count": None, "duration": 30 * 60}
    blocks: dict[str, Block] = {}
    map: dict[str, canary.TestCase] = {}
    graph: dict[canary.TestCase, list[canary.TestCase]] = {}
    for case in cases:
        graph[case] = [dep for dep in case.dependencies if dep in cases]
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ready = ts.get_ready()
        for case in ready:
            map[case.id] = case
            width = case.cpus
            extent = case.nodes * cpus_per_node
            if case.exclusive:
                width = extent
            dependencies: list[Block] = [blocks[dep.id] for dep in case.dependencies]
            blocks[case.id] = Block(
                case.id, width, math.ceil(case.runtime), extent=extent, dependencies=dependencies
            )
        ts.done(*ready)
    groupby = "extent" if batchspec["nodes"] == "same" else "auto"
    buckets: list[Bucket]
    if batchspec["duration"] is not None:
        height = math.ceil(float(batchspec["duration"]))
        logger.debug(f"Batching test cases using duration={height}")
        buckets = pack_to_height(list(blocks.values()), height=height, groupby=groupby)
    else:
        assert batchspec["count"] is not None
        count = int(batchspec["count"])
        logger.debug(f"Batching test cases using count={count}")
        if batchspec["layout"] == "atomic":
            buckets = pack_by_count_atomic(list(blocks.values()), count)
        else:
            buckets = pack_by_count(list(blocks.values()), count, groupby=groupby)
    return [TestBatch([map[block.id] for block in bucket]) for bucket in buckets]


def packed_perimeter(
    cases: Iterable[canary.TestCase], cpus_per_node: int | None = None
) -> tuple[int, int]:
    cpus_per_node = cpus_per_node or psutil.cpu_count()
    cases = sorted(cases, key=lambda c: c.size(), reverse=True)
    cpus = max(case.cpus for case in cases)
    nodes = math.ceil(cpus / cpus_per_node)
    width = nodes * cpus_per_node
    blocks: list[Block] = []
    for case in cases:
        width = case.cpus
        extent = case.nodes * cpus_per_node
        if case.exclusive:
            width = extent
        blocks.append(Block(case.id, width, math.ceil(case.runtime), extent=extent))
    packer = Packer()
    packer.pack(blocks, width=width)
    return perimeter(blocks)
