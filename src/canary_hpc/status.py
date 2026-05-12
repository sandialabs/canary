# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from collections import Counter
from typing import Any

import canary
from _canary.status import Status


class BatchStatus(Status):
    def __init__(self, children: list[canary.TestCase]) -> None:
        self._children: list[canary.TestCase] = list(children)
        self.base: Status = Status()

    @property
    def category(self) -> str:
        return self.base.category

    @property
    def outcome(self) -> str:
        return self.base.outcome

    @property
    def reason(self) -> str | None:
        return self.base.reason

    @property
    def code(self) -> int:
        return self.base.code

    @property
    def color(self) -> str:
        return self.base.color

    def asdict(self) -> dict:
        return self.base.asdict()

    def set(
        self,
        category: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.base.set(category=category, outcome=outcome, reason=reason, code=code)
        for child in self._children:
            if not child.state.is_done():
                s = child.state
                child.status = Status.BROKEN(reason=f"{child}: unexpected state {s=}")
            elif child.state.is_running():
                child.timekeeper.stop()
                child.status = Status.CANCELLED()
            elif child.state.is_done():
                child.status.set(category=category, outcome=outcome, reason=reason, code=code)

    def set_base(
        self,
        *,
        category: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        """Internal: update only the batch aggregate status."""
        self.base.set(category=category, outcome=outcome, reason=reason, code=code)

    def display_name(self, **kwargs: Any) -> str:
        def sortkey(x):
            n = 0 if x[0] == "PASS" else 2 if x[0] == "FAIL" else 1
            return (n, x[1])

        counts: Counter[tuple[str, str]] = Counter()
        present_cats: set[str] = set()

        for child in self._children:
            cat = child.status.category
            present_cats.add(cat)
            if cat == "PASS":
                counts[(cat, "PASS")] += 1
            else:
                counts[(cat, child.status.outcome)] += 1

        # Derive the batch category for display (don't trust base.category)
        derived_cat: str = "NONE"
        if "FAIL" in present_cats:
            derived_cat = "FAIL"
        elif "CANCEL" in present_cats:
            derived_cat = "CANCEL"
        elif "SKIP" in present_cats:
            derived_cat = "SKIP"
        elif "PASS" in present_cats and len(present_cats) == 1:
            derived_cat = "PASS"

        style = kwargs.get("style")
        parts: list[str] = []
        for cat, stat in sorted(counts, key=sortkey):
            count = counts[(cat, stat)]
            if style == "rich":
                color = self.base.COLOR_FOR_CATEGORY[cat]
                parts.append(f"{count} [{color}]{stat}[/{color}]")
            else:
                parts.append(f"{count} {stat}")

        return f"{derived_cat} ({', '.join(parts)})"
