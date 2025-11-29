# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import datetime
import hashlib
from graphlib import TopologicalSorter
from typing import TYPE_CHECKING
from typing import Iterable

from . import config
from .hookspec import hookimpl
from .rules import ResourceCapacityRule
from .rules import Rule
from .testspec import Mask
from .util import json_helper as json
from .util import logging
from .util.string import pluralize

if TYPE_CHECKING:
    from .config.argparsing import Parser
    from .testspec import ResolvedSpec
    from .testspec import TestSpec


logger = logging.get_logger(__name__)


def canary_select(selector: "Selector") -> list["TestSpec"]:
    """Filter test cases (mask test cases that don't meet a specific criteria)"""
    pm = logger.progress_monitor("@*{Selecting} specs")
    config.pluginmanager.hook.canary_selectstart(selector=selector)
    selector.run()
    config.pluginmanager.hook.canary_select_modifyitems(selector=selector)
    pm.done()
    config.pluginmanager.hook.canary_select_report(selector=selector)
    return selector.final_specs()


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "--show-excluded-tests",
        group="console reporting",
        command="run",
        action="store_true",
        default=False,
        help="Show names of tests that are excluded from the test session %(default)s",
    )


@hookimpl
def canary_select_report(selector: "Selector") -> None:
    excluded: list["ResolvedSpec"] = []
    for spec in selector.specs:
        if spec.mask:
            excluded.append(spec)
    n = len(selector.specs) - len(excluded)
    logger.info("@*{Selected} %d test %s" % (n, pluralize("spec", n)))
    if excluded:
        n = len(excluded)
        logger.info("@*{Excluded} %d test specs for the following reasons:" % n)
        reasons: dict[str | None, list["ResolvedSpec"]] = {}
        for spec in excluded:
            reasons.setdefault(spec.mask.reason, []).append(spec)
        keys = sorted(reasons, key=lambda x: len(reasons[x]))
        for key in reversed(keys):
            reason = key if key is None else key.lstrip()
            n = len(reasons[key])
            logger.log(logging.EMIT, f"• {reason} ({n} excluded)", extra={"prefix": ""})
            if config.getoption("show_excluded_tests"):
                for spec in reasons[key]:
                    logger.log(logging.EMIT, f"◦ {spec.display_name}", extra={"prefix": ""})


@dataclasses.dataclass(frozen=True)
class SelectorSnapshot:
    spec_set_id: str
    masked: dict[str, str]
    rules: list[str]
    created_on: str

    def serialize(self) -> str:
        return json.dumps_min(dataclasses.asdict(self))

    @classmethod
    def reconstruct(cls, serialized: str) -> "SelectorSnapshot":
        data = json.loads(serialized)
        return cls(**data)

    def is_compatible_with_specs(self, specs: list["ResolvedSpec"]) -> bool:
        """Return True if the snapshot matches the current spec set."""
        return self.spec_set_id == Selector.spec_set_id(specs)

    def apply(self, specs: list["ResolvedSpec"]) -> list["TestSpec"]:
        return finalize([spec for spec in specs if spec.id not in self.masked])


class Selector:
    def __init__(self, specs: list["ResolvedSpec"], rules: Iterable[Rule] = ()):
        self.specs: list["ResolvedSpec"] = specs
        self.rules: list[Rule] = list(rules)
        self.rules.insert(0, ResourceCapacityRule())
        self.ready = False

    def add_rule(self, rule: Rule) -> None:
        assert isinstance(rule, Rule)
        self.rules.append(rule)

    def run(self) -> None:
        for spec in self.specs:
            for rule in self.rules:
                outcome = rule(spec)
                if not outcome:
                    spec.mask = Mask.masked(outcome.reason or rule.default_reason)
                    break

        # Propagate masks
        changed: bool = True
        while changed:
            changed = False
            for spec in self.specs:
                if spec.mask:
                    continue
                if any(dep.mask for dep in spec.dependencies):
                    self.mask = Mask.masked("One or more dependencies masked")
                    changed = True

        self.ready = True

    @property
    def selected(self) -> list["TestSpec"]:
        if not self.ready:
            raise ValueError("selector.run() has not been executed")
        return self.final_specs()

    @staticmethod
    def spec_set_id(specs: list["ResolvedSpec"]) -> str:
        json_str = json.dumps_min(sorted([spec.id for spec in specs]))
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def snapshot(self) -> SelectorSnapshot:
        if not self.ready:
            raise ValueError("selector.run() has not been executed")
        spec_set_id = self.spec_set_id(self.specs)
        return SelectorSnapshot(
            spec_set_id=spec_set_id,
            masked={spec.id: spec.mask.reason for spec in self.specs if spec.mask.reason},
            rules=[r.serialize() for r in self.rules],
            created_on=datetime.datetime.now().isoformat(),
        )

    @classmethod
    def from_snapshot(cls, specs: list["ResolvedSpec"], snapshot: SelectorSnapshot) -> "Selector":
        self = cls(specs)
        for serialized_rule in snapshot.rules:
            rule = Rule.reconstruct(serialized_rule)
            self.add_rule(rule)
        return self

    def final_specs(self) -> list["TestSpec"]:
        if not self.ready:
            raise ValueError("selector.run() has not been executed")
        return finalize([spec for spec in self.specs if not spec.mask])


def finalize(resolved_specs: list["ResolvedSpec"]) -> list["TestSpec"]:
    map: dict[str, "ResolvedSpec"] = {}
    graph: dict[str, list[str]] = {}
    for resolved_spec in resolved_specs:
        map[resolved_spec.id] = resolved_spec
        graph[resolved_spec.id] = [s.id for s in resolved_spec.dependencies]
    lookup: dict[str, "TestSpec"] = {}
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ids = ts.get_ready()
        for id in ids:
            # Replace dependencies with TestSpec objects
            resolved = map[id]
            dependencies: list["TestSpec"] = [lookup[dep.id] for dep in resolved.dependencies]
            spec = resolved.finalize(dependencies)
            lookup[id] = spec
        ts.done(*ids)
    return list(lookup.values())
