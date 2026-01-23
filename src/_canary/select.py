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
import sys
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Generator
from typing import Iterable

import rich.box
from rich.console import Console
from rich.table import Table
from schema import Or
from schema import Schema

from . import config
from .config.argparsing import Parser
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


@dataclasses.dataclass(frozen=True)
class SelectorSnapshot:
    """Serializable snapshot of a completed selection run.

    ``SelectorSnapshot`` represents the minimal state required to determine whether a cached
    selection result is still valid and, if so, to reconstruct the selected tests without fully
    re-running all rules.

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
                "masked": Or({str: str}, {}),
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
        self.masked: set[str] = set()

    def add_rule(self, rule: Rule) -> None:
        assert isinstance(rule, Rule)
        self.rules.append(rule)

    def iter_rules(self) -> Generator["Rule", None, None]:
        for _, rule in sorted(enumerate(self.rules), key=lambda x: (-x[1].priority, x[0])):
            yield rule

    def run(self) -> list["ResolvedSpec"]:
        config.pluginmanager.hook.canary_selectstart(selector=self)
        self.masked.clear()
        if self.rules:
            logger.info(f"[bold]Selecting[/] specs based on {len(self.rules)} rules")
            for spec in self.specs:
                if spec.mask:
                    continue
                for rule in self.iter_rules():
                    outcome = rule(spec)
                    if not outcome:
                        spec.mask = Mask.masked(outcome.reason or rule.default_reason)
                        self.masked.add(spec.id)
                        break
        config.pluginmanager.hook.canary_select_modifyitems(selector=self)
        self.propagate()
        config.pluginmanager.hook.canary_select_report(selector=self)
        return [spec for spec in self.specs if spec.id not in self.masked]

    def propagate(self) -> None:
        # Propagate masks
        queue = deque([spec for spec in self.specs if spec.mask])
        spec_map: dict[str, "ResolvedSpec"] = {spec.id: spec for spec in self.specs}
        # Precompute reverse graph
        dependents: dict[str, list[str]] = {s.id: [] for s in self.specs}
        for s in self.specs:
            for dep in s.dependencies:
                dependents[dep.id].append(s.id)
        while queue:
            masked = queue.popleft()
            for child_id in dependents[masked.id]:
                child = spec_map[child_id]
                if not child.mask:
                    child.mask = Mask.masked("One or more dependencies masked")
                    self.masked.add(child.id)
                    queue.append(child)

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
            self.rules.append(rule)
        return self

    @staticmethod
    def setup_parser(parser: "Parser", tagged: str = "required") -> None:
        group = parser.get_group("test spec selection")
        group.add_argument(
            "-k",
            dest="keyword_exprs",
            metavar="expression",
            action="append",
            help="Restrict selection to tests matching expression. "
            "For example: `-k 'key1 and not key2'`.  The keyword ``:all:`` matches all tests",
        )
        group.add_argument(
            "--owner",
            dest="owners",
            action="append",
            help="Restrict selection to tests owned by 'owner'",
        )
        group.add_argument(
            "-p",
            dest="parameter_expr",
            metavar="expression",
            help="Restrict selection to tests matching the paramter expression. "
            "For example: '-p cpus=8' or '-p cpus<8'",
        )
        group.add_argument(
            "--regex",
            dest="regex_filter",
            metavar="regex",
            help="Restrict selection to tests containing the regular expression regex in at "
            "least 1 of its file assets.  regex is a python regular expression, see "
            "https://docs.python.org/3/library/re.html",
        )
        if tagged == "required":
            group.add_argument("tag", help="Name this selection 'tag'")
        elif tagged == "optional":
            group.add_argument("--tag", help="Name this selection 'tag'")


class RuntimeSelector:
    """Apply rule-based masking to a set of test cases."""

    def __init__(
        self, cases: list["TestCase"], workspace: Path, rules: Iterable[RuntimeRule] = ()
    ) -> None:
        self.cases = cases
        self.workspace = workspace
        self.rules: list[RuntimeRule] = list(rules)
        self.masked: set[str] = set()

    def add_rule(self, rule: RuntimeRule) -> None:
        assert isinstance(rule, RuntimeRule)
        self.rules.append(rule)

    def iter_rules(self) -> Generator["RuntimeRule", None, None]:
        for _, rule in sorted(enumerate(self.rules), key=lambda x: (-x[1].priority, x[0])):
            yield rule

    def run(self) -> None:
        self.masked.clear()
        pm = logger.progress_monitor("[bold]Selecting[/] test cases based on runtime environment")
        config.pluginmanager.hook.canary_rtselectstart(selector=self)
        for case in self.cases:
            if case.mask:
                continue
            for rule in self.iter_rules():
                outcome = rule(case)
                if not outcome:
                    case.mask = Mask.masked(reason=outcome.reason or rule.default_reason)
                    self.masked.add(case.id)
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
        command=("run", "find", "selection"),
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
    if not selector.masked:
        return
    excluded: list["ResolvedSpec"] = []
    for spec in selector.specs:
        if spec.id in selector.masked:
            excluded.append(spec)
    logger.info("[bold]Selected[/] %d test specs" % (len(selector.specs) - len(selector.masked)))
    if excluded:
        n = len(selector.masked)
        show_excluded_tests = config.getoption("show_excluded_tests") or config.get("debug")
        n = len(excluded)
        logger.info("[bold]Excluded[/] %d test %s during selection" % (n, pluralize("spec", n)))
        table = Table(show_header=True, header_style="bold", box=rich.box.SIMPLE_HEAD)
        table.add_column("Reason", no_wrap=False)
        table.add_column("Count", no_wrap=True, ratio=2, justify="right")
        reasons: dict[str | None, list["ResolvedSpec"]] = {}
        for spec in excluded:
            reasons.setdefault(spec.mask.reason, []).append(spec)
        keys = sorted(reasons, key=lambda x: len(reasons[x]))
        for key in reversed(keys):
            reason = key if key is None else key.lstrip()
            table.add_row(reason, str(len(reasons[key])))
        console = Console(file=sys.stderr)
        console.print(table)
        if show_excluded_tests:
            for key in reversed(keys):
                reason = "Unspecified" if key is None else key.lstrip()
                console.print(f"[bold]{reason}[/]")
                for spec in reasons[key]:
                    console.print(f"  • {spec.display_name(style='rich')}")


@hookimpl
def canary_rtselect_report(selector: "RuntimeSelector") -> None:
    if not selector.masked:
        return
    excluded: list["TestCase"] = [case for case in selector.cases if case.id in selector.masked]
    n = len(selector.masked)
    if excluded:
        n = len(excluded)
        reasons: dict[str | None, list["TestCase"]] = {}
        for case in excluded:
            reasons.setdefault(case.mask.reason, []).append(case)
        keys = sorted(reasons, key=lambda x: len(reasons[x]))
        logger.info("[bold]Excluded[/] %d test cases" % n)
        table = Table(show_header=True, header_style="bold", box=rich.box.SIMPLE_HEAD)
        table.add_column("Reason", no_wrap=False)
        table.add_column("Count", no_wrap=True, ratio=2, justify="right")
        for key in reversed(keys):
            reason = "Unspecified" if key is None else key.lstrip()
            table.add_row(reason, str(len(reasons[key])))
        console = Console(file=sys.stderr)
        console.print(table)
