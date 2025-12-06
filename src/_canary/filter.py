# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
from collections import deque
from typing import TYPE_CHECKING
from typing import Iterable

from . import config
from .hookspec import hookimpl
from .rules import ContextRule
from .rules import ResourceCapacityRule
from .util import logging
from .util.string import pluralize

if TYPE_CHECKING:
    from .testcase import TestCase


logger = logging.get_logger(__name__)


class ExecutionContextFilter:
    """Apply rule-based masking to a set of test cases."""

    def __init__(self, cases: list["TestCase"], rules: Iterable[ContextRule] = ()) -> None:
        self.cases = cases
        self.rules: list[ContextRule] = list(rules)
        self.rules.append(ResourceCapacityRule())

    def add_rule(self, rule: ContextRule) -> None:
        assert isinstance(rule, ContextRule)
        self.rules.append(rule)

    def run(self) -> None:
        pm = logger.progress_monitor("@*{Filtering} cases based on execution context")
        config.pluginmanager.hook.canary_contextfilterstart(contextfilter=self)
        for case in self.cases:
            for rule in self.rules:
                outcome = rule(case)
                if not outcome:
                    case.status.set("SKIPPED", reason=outcome.reason or rule.default_reason)
                    break
        config.pluginmanager.hook.canary_contextfilter_modifyitems(contextfilter=self)
        self.propagate()
        pm.done()
        config.pluginmanager.hook.canary_contextfilter_report(contextfilter=self)
        return

    def propagate(self) -> None:
        # Propagate skipped tests
        queue = deque([c for c in self.cases if c.status.category not in ("READY", "PENDING")])
        case_map: dict[str, "TestCase"] = {case.id: case for case in self.cases}
        # Precompute reverse graph
        dependents: dict[str, list[str]] = {case.id: [] for case in self.cases}
        for case in self.cases:
            for dep in case.spec.dependencies:
                dependents[dep.id].append(case.id)
        while queue:
            excluded = queue.popleft()
            for child_id in dependents[excluded.id]:
                child = case_map[child_id]
                if child.status.category in ("READY", "PENDING"):
                    stat = excluded.status.category.lower()
                    child.status.set("SKIPPED", f"One or more dependencies {stat}")
                    queue.append(child)
        return


@hookimpl
def canary_contextfilter_report(contextfilter: "ExecutionContextFilter") -> None:
    excluded: list["TestCase"] = []
    for case in contextfilter.cases:
        if case.status.category not in ("READY", "PENDING"):
            excluded.append(case)
    n = len(contextfilter.cases) - len(excluded)
    logger.info("@*{Selected} %d test %s" % (n, pluralize("case", n)))
    if excluded:
        n = len(excluded)
        logger.info("@*{Excluded} %d test cases for the following reasons:" % n)
        reasons: dict[str | None, list["TestCase"]] = {}
        for case in excluded:
            reasons.setdefault(case.status.reason, []).append(case)
        keys = sorted(reasons, key=lambda x: len(reasons[x]))
        for key in reversed(keys):
            reason = key if key is None else key.lstrip()
            n = len(reasons[key])
            logger.log(logging.EMIT, f"• {reason} ({n} excluded)", extra={"prefix": ""})
