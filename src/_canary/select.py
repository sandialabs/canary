# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Selection Phase for Canary Test Execution
=========================================

This module implements the selection stage of the Canary test lifecycle.  Selection applies a
sequence of rules to mask (exclude) test specifications based on resource availability,
user-defined criteria, and dependency relationships. The result of selection is a stable, filtered
list of ``TestSpec`` instances ready for execution.

Overview
--------

The selection flow is:

    selector = Selector(specs, workspace, rules)
    final_specs = canary_select(selector)

Selection performs three primary actions:

1. **Rule Evaluation** — Each ``ResolvedSpec`` is evaluated against each
   ``Rule``. If any rule fails, the spec receives a ``Mask`` with the reason.

2. **Mask Propagation** — If a spec is masked, all specs depending on it are also masked.

3. **Finalization** — Unmasked ``ResolvedSpec`` objects are topologically sorted and finalized into
``TestSpec`` instances.

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
from graphlib import TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Iterable

from schema import Schema

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
    """Run the selection phase on the provided selector.

    This function executes the standard selection lifecycle:
    plugin start hooks, rule execution, mask propagation,
    plugin modification hooks, and reporting hooks.

    Args:
        selector: A ``Selector`` instance configured with specs and rules.

    Returns:
        A list of finalized ``TestSpec`` instances ready for execution.
    """
    config.pluginmanager.hook.canary_selectstart(selector=selector)
    selector.run()
    config.pluginmanager.hook.canary_select_modifyitems(selector=selector)
    config.pluginmanager.hook.canary_select_report(selector=selector)
    return selector.final_specs()


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
        command="run",
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
    """Serializable snapshot of a completed selection run.

    ``SelectorSnapshot`` represents the minimal state required to determine whether a cached
    selection result is still valid and, if so, to reconstruct the selected tests without fully
    re-running all rules.

    Attributes: spec_set_id: Stable SHA-256 hash identifying the original spec set.  masked:
    Mapping of masked spec IDs to their mask reasons.  rules: A list of serialized rules that were
    applied.  created_on: ISO-8601 timestamp of snapshot creation.
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

    def apply(self, specs: list["ResolvedSpec"]) -> list["TestSpec"]:
        return finalize([spec for spec in specs if spec.id not in self.masked])


class Selector:
    """Apply rule-based masking to a set of resolved specifications.

    ``Selector`` is responsible for evaluating rules against each ``ResolvedSpec``, propagating
    masks through dependency graphs, and finalizing the resulting test specifications.

    Args:
        specs: The list of ``ResolvedSpec`` objects to select from.
        rules: Optional iterable of ``Rule`` instances. A
            ``ResourceCapacityRule`` is always prepended unless overridden.

    Attributes:
        specs: The input list of resolved specs.
        rules: The rule sequence applied during selection.
        ready: Whether selection has been executed via :meth:`run`.
    """

    def __init__(self, specs: list["ResolvedSpec"], workspace: Path, rules: Iterable[Rule] = ()):
        self.specs: list["ResolvedSpec"] = specs
        self.workspace = workspace
        self.rules: list[Rule] = list(rules)
        self.rules.insert(0, ResourceCapacityRule())
        self.ready = False

    def add_rule(self, rule: Rule) -> None:
        assert isinstance(rule, Rule)
        self.rules.append(rule)

    def run(self) -> None:
        pm = logger.progress_monitor("@*{Selecting} specs based on %d rule sets" % len(self.rules))
        for spec in self.specs:
            if spec.mask:
                continue
            for rule in self.rules:
                outcome = rule(spec)
                if not outcome:
                    spec.mask = Mask.masked(outcome.reason or rule.default_reason)
                    break
        self.ready = True
        pm.done()

    @property
    def selected(self) -> list["TestSpec"]:
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
    def from_snapshot(
        cls, specs: list["ResolvedSpec"], workspace: Path, snapshot: SelectorSnapshot
    ) -> "Selector":
        self = cls(specs, workspace)
        for serialized_rule in snapshot.rules:
            rule = Rule.reconstruct(serialized_rule)
            self.add_rule(rule)
        return self

    def final_specs(self) -> list["TestSpec"]:
        if not self.ready:
            raise ValueError("selector.run() has not been executed")
        return finalize(self.specs)


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


def finalize(resolved_specs: list["ResolvedSpec"]) -> list["TestSpec"]:
    """Finalize resolved specs into topologically ordered test specs.

    This function constructs the final ``TestSpec`` objects from the dependency graph defined by
    ``ResolvedSpec.dependencies``. It ensures a deterministic topological order and replaces
    dependency references with the finalized ``TestSpec`` instances.

    Args:
        resolved_specs: A list of unmasked ``ResolvedSpec`` objects.

    Returns:
        A list of ``TestSpec`` instances in dependency-resolved order.
    """
    spec_map: dict[str, "ResolvedSpec"] = {}
    graph: dict[str, list[str]] = {}
    # calling propagate_masks should be unnecessary at this point
    propagate_masks(resolved_specs)
    for resolved_spec in resolved_specs:
        if resolved_spec.mask:
            continue
        spec_map[resolved_spec.id] = resolved_spec
        graph[resolved_spec.id] = [s.id for s in resolved_spec.dependencies]
    lookup: dict[str, "TestSpec"] = {}
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ids = ts.get_ready()
        for id in ids:
            # Replace dependencies with TestSpec objects
            resolved = spec_map[id]
            dependencies: list["TestSpec"] = [lookup[dep.id] for dep in resolved.dependencies]
            spec = resolved.finalize(dependencies)
            lookup[id] = spec
        ts.done(*ids)
    return list(lookup.values())
