# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from collections import Counter
from dataclasses import dataclass
from dataclasses import field
from typing import Any

import canary
from _canary.status import Category
from _canary.status import Outcome
from _canary.status import Status


@dataclass(slots=True)
class BatchStatus:
    """Aggregate status for a batch job.

    - `base` is the batch job's own terminal status (submission errors, etc.).
    - display/derived semantics are computed from child testcases.
    """

    children: list[canary.TestCase]
    base: Status = field(default_factory=Status)

    # ---- delegate common status API to base (or derived, see below) ----
    @property
    def category(self) -> Category:
        return self.base.category

    @property
    def outcome(self) -> Outcome:
        return self.base.outcome

    @property
    def reason(self) -> str | None:
        return self.base.reason

    @property
    def code(self) -> int:
        return self.base.code

    def is_success(self) -> bool:
        return self.base.is_success()

    def is_failure(self) -> bool:
        return self.base.is_failure()

    def is_skipped(self) -> bool:
        return self.base.is_skipped()

    def is_cancelled(self) -> bool:
        return self.base.is_cancelled()

    def asdict(self) -> dict[str, Any]:
        return self.base.asdict()

    # ---- updating ----
    def set_base(
        self,
        *,
        category: Category | str | None = None,
        outcome: Outcome | str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        """Update only the batch job's own status."""
        self.base.set(category=category, outcome=outcome, reason=reason, code=code)

    def set(
        self,
        *,
        category: Category | str | None = None,
        outcome: Outcome | str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        """Set the batch base status and propagate to children that are DONE.

        NOTE: We should not mutate non-DONE children results except to mark them cancelled/broken
        if they were unexpectedly still RUNNING at batch end.
        """
        self.set_base(category=category, outcome=outcome, reason=reason, code=code)

        for child in self.children:
            if child.state.is_running():
                # Child still running while batch finalizes -> cancel it
                child.status = Status.CANCELLED(reason="Batch finalized while child still running")
                child.state.phase = child.state.phase.__class__.DONE  # or JobPhase.DONE if imported
                continue

            if not child.state.is_done():
                # Child never ran / still pending -> mark broken (or blocked)
                child.status = Status.BROKEN(
                    reason=f"{child}: unexpected phase={child.state.phase}"
                )
                child.state.phase = child.state.phase.__class__.DONE
                continue

            # Child is DONE: optionally overwrite its terminal outcome to match batch
            # (This is your old behavior; you may later decide not to do this.)
            child.status.set(category=category, outcome=outcome, reason=reason, code=code)

    # ---- aggregation for reporting ----
    def _derived_category(self) -> Category:
        """Derive an overall category from children."""
        present = {c.status.category for c in self.children}

        if Category.FAIL in present:
            return Category.FAIL
        if Category.CANCEL in present:
            return Category.CANCEL
        if Category.SKIP in present:
            return Category.SKIP
        if present == {Category.PASS}:
            return Category.PASS
        return Category.NONE

    def display_name(self, **kwargs: Any) -> str:
        """Return summary string like:
        FAIL (2 FAILED, 1 TIMEOUT, 3 SUCCESS)
        """
        style = kwargs.get("style", "none")

        def sortkey(k: tuple[Category, Outcome]) -> tuple[int, str]:
            cat, out = k
            n = 0 if cat is Category.PASS else 2 if cat is Category.FAIL else 1
            return (n, out.name)

        counts: Counter[tuple[Category, Outcome]] = Counter()
        for child in self.children:
            counts[(child.status.category, child.status.outcome)] += 1

        parts: list[str] = []
        for cat, out in sorted(counts.keys(), key=sortkey):
            n = counts[(cat, out)]
            label = out.name
            if style == "rich":
                color = cat.rich_color()
                parts.append(f"{n} [{color}]{label}[/]")
            else:
                parts.append(f"{n} {label}")

        derived_cat = self._derived_category()
        return f"{derived_cat.value} ({', '.join(parts)})"
