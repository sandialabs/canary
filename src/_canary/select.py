# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Selection Phase for Canary Test Execution
=========================================

This module implements the election stage of the Canary test lifecycle.  Selection applies a
sequence of rules to mask (exclude) test specifications based on resource availability,
user-defined criteria, and dependency relationships. The result of selection is a stable, filtered
list of ``ResolvedSpec`` instances ready for execution.

Overview
--------

The selection flow is:

    selector = Selector(specs, workspace, rules)
    final_specs = canary_select(selector)

Selection performs three primary actions:

1. **Rule Evaluation** — Each ``ResolvedSpec`` is evaluated against each
   ``Rule``. If any rule fails, the spec receives a ``Mask`` with the reason.

2. **Mask Propagation** — If a spec is masked, all specs depending on it are also masked.

``ResolvedSpec`` instances.

Caching and Snapshots
---------------------

Selection results can be cached using ``SelectorSnapshot``. A snapshot includes:

* The stable hash of the input spec set
* A mapping of masked spec IDs to their reasons
* The serialized rule set
* A timestamp

Snapshots allow callers to determine whether cached selections remain valid
after a workspace changes.

Plugin Integration
------------------

Plugins participate in the selection lifecycle via:

* ``canary_selectstart`` — Mutate or inspect the ``Selector`` before execution.
* ``canary_select_modifyitems`` — Adjust masked/unmasked items after rules run.
* ``canary_select_report`` — Emit reporting data after selection.

This keeps the selection engine deterministic while allowing flexible
extensibility.

"""

import dataclasses
import datetime
import hashlib
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Iterable

from schema import Schema

from . import config
from .hookspec import hookimpl
from .rules import Rule
from .rules import RuntimeRule
from .status import Status
from .testspec import Mask
from .util import json_helper as json
from .util import logging
from .util.string import pluralize

if TYPE_CHECKING:
    from .config.argparsing import Parser
    from .testcase import TestCase
    from .testspec import ResolvedSpec


logger = logging.get_logger(__name__)


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    """Register Selection-related command-line options.

    This hook adds ``--show-excluded-tests`` to the console reporting
    group for the ``canary run`` command.

    Args:
        parser: The argument parser used to register command-line flags.
    """
    parser.add_argument(
        "--show-excluded-tests",
        group="console reporting",
        command=("run", "find"),
        action="store_true",
        default=False,
        help="Show names of tests that are excluded from the test session %(default)s",
    )


@hookimpl
def canary_select_report(selector: "Selector") -> None:
    """Emit a report summarizing which specs were selected or excluded.

    Reporting includes the count of selected and excluded tests, grouped
    by mask reason. If ``--show-excluded-tests`` was provided, individual
    spec names are also emitted.

    Args:
        selector: The ``Selector`` instance whose results are being reported.
    """
    select_report(selector.specs)


@dataclasses.dataclass(frozen=True)
class SelectorSnapshot:
    """Serializable snapshot of a completed selection run.

    ``SelectorSnapshot`` represents the minimal state required to determine whether a cached
    selection result is still valid and, if so, to reconstruct the selected tests without fully
    re-running all rules.

    Attributes:
      spec_set_id: Stable SHA-256 hash identifying the original spec set.
      masked: Mapping of masked spec IDs to their mask reasons.  rules: A list of serialized rules
        that were applied.
      created_on: ISO-8601 timestamp of snapshot creation.
    """

    spec_set_id: str
    masked: dict[str, str]
    rules: list[str]
    created_on: str

    def serialize(self) -> str:
        return json.dumps_min(dataclasses.asdict(self))

    @staticmethod
    def schema() -> Schema:
        s = Schema(
            {
                "spec_set_id": str,
                "masked": {str: str},
                "rules": [str],
                "created_on": str,
            }
        )
        return s

    @classmethod
    def reconstruct(cls, serialized: str) -> "SelectorSnapshot":
        data = json.loads(serialized)
        SelectorSnapshot.schema().validate(data)
        return cls(**data)

    def is_compatible_with_specs(self, specs: list["ResolvedSpec"]) -> bool:
        """Return True if the snapshot matches the current spec set."""
        return self.spec_set_id == Selector.spec_set_id(specs)

    def apply(self, specs: list["ResolvedSpec"]) -> None:
        for spec in specs:
            if mask := self.masked.get(spec.id):
                spec.mask = Mask.masked(mask)


class Selector:
    """Apply rule-based masking to a set of resolved specifications.

    ``Selector`` is responsible for evaluating rules against each ``ResolvedSpec``, propagating
    masks through dependency graphs, and finalizing the resulting test specifications.

    Args:
        specs: The list of ``ResolvedSpec`` objects to select from.
        rules: Optional iterable of ``Rule`` instances.

    Attributes:
        specs: The input list of resolved specs.
        rules: The rule sequence applied during selection.
    """

    def __init__(self, specs: list["ResolvedSpec"], workspace: Path, rules: Iterable[Rule] = ()):
        self.specs = specs
        self.workspace = workspace
        self.rules: list[Rule] = list(rules)

    def add_rule(self, rule: Rule) -> None:
        assert isinstance(rule, Rule)
        self.rules.append(rule)

    def run(self) -> None:
        logger.debug("@*{Selecting} specs based on rules")
        config.pluginmanager.hook.canary_selectstart(selector=self)
        for spec in self.specs:
            if spec.mask:
                continue
            for rule in self.rules:
                outcome = rule(spec)
                if not outcome:
                    spec.mask = Mask.masked(outcome.reason or rule.default_reason)
                    break
        config.pluginmanager.hook.canary_select_modifyitems(selector=self)
        config.pluginmanager.hook.canary_select_report(selector=self)
        return

    @staticmethod
    def spec_set_id(specs: list["ResolvedSpec"]) -> str:
        json_str = json.dumps_min(sorted([spec.id for spec in specs]))
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def snapshot(self) -> SelectorSnapshot:
        spec_set_id = self.spec_set_id(self.specs)
        return SelectorSnapshot(
            spec_set_id=spec_set_id,
            masked={spec.id: spec.mask.reason for spec in self.specs if spec.mask.reason},
            rules=[r.serialize() for r in self.rules],
            created_on=datetime.datetime.now().isoformat(),
        )

    @classmethod
    def from_snapshot(
        cls, specs: list["ResolvedSpec"], workspace: Path, snapshot: SelectorSnapshot
    ) -> "Selector":
        self = cls(specs, workspace)
        for serialized_rule in snapshot.rules:
            rule = Rule.reconstruct(serialized_rule)
            self.add_rule(rule)
        return self


class RuntimeSelector:
    """Apply rule-based masking to a set of test cases."""

    def __init__(
        self, cases: list["TestCase"], workspace: Path, rules: Iterable[RuntimeRule] = ()
    ) -> None:
        self.cases = cases
        self.workspace = workspace
        self.rules: list[RuntimeRule] = list(rules)

    def add_rule(self, rule: RuntimeRule) -> None:
        assert isinstance(rule, RuntimeRule)
        self.rules.append(rule)

    def run(self) -> None:
        pm = logger.progress_monitor("@*{Selecting} test cases based on runtime environment")
        config.pluginmanager.hook.canary_rtselectstart(selector=self)
        for case in self.cases:
            if case.mask:
                continue
            for rule in self.rules:
                outcome = rule(case)
                if not outcome:
                    case.mask = Mask.masked(reason=outcome.reason or rule.default_reason)
                    break
        config.pluginmanager.hook.canary_rtselect_modifyitems(selector=self)
        self.propagate()
        for case in self.cases:
            if not case.mask:
                case.status = Status.PENDING()
                case.timekeeper.reset()
                case.measurements.reset()
        pm.done()
        config.pluginmanager.hook.canary_rtselect_report(selector=self)
        return

    def propagate(self) -> None:
        # Propagate skipped/broken tests
        queue = deque([c for c in self.cases if c.mask and c.status.state in ("READY", "PENDING")])
        case_map: dict[str, "TestCase"] = {case.id: case for case in self.cases}
        # Precompute reverse graph
        dependents: dict[str, list[str]] = {case.id: [] for case in self.cases}
        for case in self.cases:
            for dep in case.spec.dependencies:
                dependents.setdefault(dep.id, []).append(case.id)
        while queue:
            excluded = queue.popleft()
            for child_id in dependents[excluded.id]:
                child = case_map[child_id]
                if not child.mask:
                    child.mask = Mask.masked(reason="One or more dependencies do not have results")
                    queue.append(child)
        return


def propagate_masks(specs: list["ResolvedSpec"]):
    # Propagate masks
    queue = deque([spec for spec in specs if spec.mask])
    spec_map: dict[str, "ResolvedSpec"] = {spec.id: spec for spec in specs}
    # Precompute reverse graph
    dependents: dict[str, list[str]] = {s.id: [] for s in specs}
    for s in specs:
        for dep in s.dependencies:
            dependents[dep.id].append(s.id)
    while queue:
        masked = queue.popleft()
        for child_id in dependents[masked.id]:
            child = spec_map[child_id]
            if not child.mask:
                child.mask = Mask.masked("One or more dependencies masked")
                queue.append(child)


def select_report(specs: list["ResolvedSpec"]) -> None:
    """Emit a report summarizing which specs were selected or excluded.

    Reporting includes the count of selected and excluded tests, grouped
    by mask reason. If ``--show-excluded-tests`` was provided, individual
    spec names are also emitted.

    """
    excluded: list["ResolvedSpec"] = []
    for spec in specs:
        if spec.mask:
            excluded.append(spec)
    n = len(specs) - len(excluded)
    logger.info("@*{Selected} %d of %d test %s " % (n, len(specs), pluralize("spec", n)))
    show_excluded_tests = config.getoption("show_excluded_tests") or config.get("debug")
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
            if show_excluded_tests:
                for spec in reasons[key]:
                    logger.log(logging.EMIT, f"  ◦ {spec.display_name}", extra={"prefix": ""})


@hookimpl
def canary_rtselect_report(selector: "RuntimeSelector") -> None:
    excluded: list["TestCase"] = []
    for case in selector.cases:
        if case._mask:
            # A case can have its own mask, different than the specs, it is only assigned during
            # rtselect
            excluded.append(case)
    unmasked = [case for case in selector.cases if not case.mask]
    n = len(unmasked) - len(excluded)
    logger.info("@*{Selected} %d of %d test %s " % (n, len(unmasked), pluralize("case", n)))
    if excluded:
        n = len(excluded)
        logger.info("@*{Excluded} %d test cases for the following reasons:" % n)
        reasons: dict[str | None, list["TestCase"]] = {}
        for case in excluded:
            reasons.setdefault(case.mask.reason, []).append(case)
        keys = sorted(reasons, key=lambda x: len(reasons[x]))
        for key in reversed(keys):
            reason = key if key is None else key.lstrip()
            n = len(reasons[key])
            logger.log(logging.EMIT, f"• {reason} ({n} excluded)", extra={"prefix": ""})
