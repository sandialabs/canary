# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import math
from graphlib import TopologicalSorter
from typing import Iterable
from typing import Literal

import canary
from _canary.util import cpu_count

from . import binpack
from .batchspec import BatchSpec

logger = canary.get_logger(__name__)


def batch_testcases(
    *,
    cases: list["canary.TestCase"],
    nodes: Literal["any", "same"] = "any",
    layout: Literal["flat", "atomic"] = "flat",
    count: int | None = None,
    duration: float | None = None,
    width: int | None = None,
    cpus_per_node: int | None = None,
) -> list[BatchSpec]:
    if duration is None and count is None:
        duration = 30 * 60  # 30 minute default
    elif duration is not None and count is not None:
        raise ValueError("duration and count are mutually exclusive")

    bins: list[binpack.Bin] = []

    grouper: binpack.GrouperType | None = None
    if nodes == "same":
        grouper = GroupByNodes(cpus_per_node=cpus_per_node)
    # The binpacking code works with Block not TestCase.
    blocks: dict[str, binpack.Block] = {}
    lookup: dict[str, canary.TestCase] = {case.id: case for case in cases}
    graph: dict[str, list[str]] = {}
    for case in cases:
        graph[case.id] = [dep.id for dep in case.dependencies if dep.id in lookup]
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ready = ts.get_ready()
        for id in ready:
            case = lookup[id]
            assert case.id == id
            dependencies: list[binpack.Block] = [blocks[dep.id] for dep in case.dependencies]
            blocks[case.id] = binpack.Block(
                case.id, case.cpus, math.ceil(case.runtime), dependencies=dependencies
            )
        ts.done(*ready)
    if duration is not None:
        height = math.ceil(float(duration))
        logger.debug(f"Batching test cases using duration={height}")
        bins = binpack.pack_to_height(
            list(blocks.values()), height=height, width=width, grouper=grouper
        )
    else:
        assert isinstance(count, int)
        logger.debug(f"Batching test cases using count={count}")
        if layout == "atomic":
            bins = binpack.pack_by_count_atomic(list(blocks.values()), count)
        else:
            bins = binpack.pack_by_count(list(blocks.values()), count, grouper=grouper)
    specs = [BatchSpec(cases=[lookup[block.id] for block in bin]) for bin in bins]
    return specs


def packed_perimeter(
    cases: Iterable[canary.TestCase], cpus_per_node: int | None = None
) -> tuple[int, int]:
    cpus_per_node = cpus_per_node or cpu_count()
    cases = sorted(cases, key=lambda c: c.size(), reverse=True)
    cpus = max(case.cpus for case in cases)
    nodes = math.ceil(cpus / cpus_per_node)
    width = nodes * cpus_per_node
    blocks: list[binpack.Block] = []
    for case in cases:
        blocks.append(binpack.Block(case.id, case.cpus, math.ceil(case.runtime)))
    packer = binpack.Packer()
    packer.pack(blocks, width=width)
    return binpack.perimeter(blocks)


class GroupByNodes:
    def __init__(self, cpus_per_node: int | None) -> None:
        self.cpus_per_node: int = cpus_per_node or cpu_count()

    def __call__(self, blocks: list[binpack.Block]) -> list[list[binpack.Block]]:
        groups: dict[int, list[binpack.Block]] = {}
        for block in blocks:
            nodes_reqd = math.ceil(block.width / self.cpus_per_node)
            groups.setdefault(nodes_reqd, []).append(block)
        return list(groups.values())


class BatchNotFound(Exception):
    pass
