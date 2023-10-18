import json
import os
from typing import Any
from typing import Optional
from typing import TextIO
from typing import Union

from ..util import graph
from ..util import tty
from ..util.collections import defaultlist
from ..util.filesystem import mkdirp
from ..util.graph import TopologicalSorter
from .testcase import TestCase


class _Partition(set):
    @property
    def cputime(self):
        return sum(case.size * case.runtime for case in self if not case.skip)

    @property
    def runtime(self):
        return sum(case.runtime for case in self if not case.skip)

    @property
    def size(self):
        return len(self)


class Partition(list):
    def __init__(
        self, partition: Union[list[TestCase], _Partition], rank: int, group_size: int
    ) -> None:
        self.rank = (rank, group_size)
        for case in partition:
            for dep in case.dependencies:
                if dep not in partition:
                    raise ValueError(f"{case}: missing dependency: {dep}")
        self.extend(graph.static_order(list(partition)))

    @property
    def ready(self):
        return True

    @property
    def size(self):
        return max(case.size for case in self if not case.skip)

    @property
    def cputime(self):
        return sum(case.size * case.runtime for case in self if not case.skip)

    @property
    def runtime(self):
        return sum(case.runtime for case in self if not case.skip)

    def run(self, log_level: Optional[int] = None) -> dict[str, dict]:
        attrs = {}
        for case in self:
            attrs[case.fullname] = case.run(log_level=log_level)
        return attrs

    def kill(self):
        for case in self:
            case.kill()


def group_testcases(cases: list[TestCase]):
    groups: list[set[TestCase]] = [{case} | set(case.dependencies) for case in cases]
    for (i, group) in enumerate(groups):
        for (j, other) in enumerate(groups):
            if i != j and group & other:
                group.update(other)
                other.clear()
    return sorted(filter(None, groups), key=lambda g: -len(g))


def partition_n(cases, n=8) -> list[Partition]:
    groups = group_testcases(cases)
    partitions = defaultlist(_Partition, n)
    for group in groups:
        partition = min(partitions, key=lambda p: p.cputime)
        partition.update(group)
    return [Partition(p, i, n) for i, p in enumerate(partitions)]


def partition_t(cases, t=60 * 30) -> list[Partition]:
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
    return [Partition(p, i, n) for i, p in enumerate(partitions)]


def load_partition(path: str) -> Partition:
    with open(path, "r") as fh:
        data = json.load(fh)

    ts: TopologicalSorter = TopologicalSorter()
    for (id, kwds) in data["cases"].items():
        ts.add(id, *kwds["dependencies"])
    cases: dict[str, TestCase] = {}
    for id in ts.static_order():
        kwds = data["cases"][id]
        dependencies = kwds.pop("dependencies")
        case = TestCase.from_dict(kwds)
        case.dependencies = [cases[dep] for dep in dependencies]
        cases[case.id] = case
    i, n = data["rank"]
    return Partition(list(cases.values()), i, n)


def dump_partitions(
    partitions: list[Partition], dest: str = "TestPartitions"
) -> list[str]:
    files = []
    mkdirp(dest)
    n = len(partitions)
    for i, partition in enumerate(partitions):
        file = os.path.join(dest, f"batch.json.{n}.{i}")
        files.append(os.path.abspath(file))
        with open(file, "w") as fh:
            dump_partition(partition, fh)
    return files


def dump_partition(partition: Partition, fh: TextIO) -> None:
    cases: dict[str, Any] = {}
    for case in partition:
        cases[case.id] = case.asdict()
        cases[case.id]["dependencies"] = [dep.id for dep in case.dependencies]
    data = {"rank": list(partition.rank), "cases": cases}
    json.dump(data, fh, indent=2)


def merge(files: list[str]) -> list[TestCase]:
    tty.emit(f"Merging partitioned test results from {len(files)} partitions\n")
    cases: dict[str, TestCase] = {}
    for file in files:
        data = json.load(open(file))
        for case_vars in data:
            case = TestCase.from_dict(case_vars)
            if case.fullname not in cases:
                cases[case.fullname] = case
            else:
                other = cases[case.fullname]
                if other.skip.reason == "deselected by partition map":
                    cases[case.fullname] = case
    return list(cases.values())
