import json
from typing import Any
from typing import TextIO

from .test import TestCase
from .util.graph import TopologicalSorter


def dump(cases: list[TestCase], fh: TextIO, batches=None) -> None:
    index: dict[str, Any] = {}
    indexed: dict[str, Any] = index.setdefault("cases", {})
    for case in cases:
        indexed[case.id] = case.asdict()
        indexed[case.id]["dependencies"] = [dep.id for dep in case.dependencies]
    index["batches"] = None
    if batches is not None:
        assert isinstance(batches, list)
        _batches: list[list[str]] = []
        for batch in batches:
            case_ids = [case.id for case in batch]
            _batches.append(case_ids)
        index["batches"] = _batches
    json.dump({"index": index}, fh)


def load(fh: TextIO) -> list[TestCase]:
    fd = json.load(fh)
    index = fd["index"]
    ts: TopologicalSorter = TopologicalSorter()
    tcases = index.pop("cases")
    for id, kwds in tcases.items():
        ts.add(id, *kwds["dependencies"])
    cases: dict[str, TestCase] = {}
    for id in ts.static_order():
        kwds = tcases[id]
        dependencies = kwds.pop("dependencies")
        case = TestCase.from_dict(kwds)
        case.dependencies = [cases[dep] for dep in dependencies]
        cases[case.id] = case
    return list(cases.values())
