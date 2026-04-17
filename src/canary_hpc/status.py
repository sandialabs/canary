# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from collections import Counter
from typing import Any

import canary
from _canary.status import Status


class BatchStatus:
    def __init__(self, children: list[canary.TestCase]) -> None:
        self._children: list[canary.TestCase] = list(children)
        self.base_status: Status
        for child in self._children:
            if any(dep not in self._children for dep in child.dependencies):
                self.base_status = Status.PENDING()
                break
        else:
            self.base_status = Status.READY()

    @property
    def state(self) -> str:
        return self.base_status.state

    @property
    def category(self) -> str:
        return self.base_status.category

    @property
    def status(self) -> str:
        return self.base_status.status

    @property
    def reason(self) -> str | None:
        return self.base_status.reason

    def is_terminal(self) -> bool:
        return self.base_status.is_terminal()

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
                counts[(cat, child.status.status)] += 1

        # Derive the batch category for display (don’t trust base_status.category)
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
                color = self.base_status.COLOR_FOR_CATEGORY[cat]
                parts.append(f"{count} [{color}]{stat}[/{color}]")
            else:
                parts.append(f"{count} {stat}")

        return f"{derived_cat} ({', '.join(parts)})"

    @property
    def color(self) -> str:
        return self.base_status.color

    def asdict(self) -> dict:
        return self.base_status.asdict()

    def set(
        self,
        state: str | None = None,
        category: str | None = None,
        status: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.base_status.set(
            state=state, category=category, status=status, reason=reason, code=code
        )
        for child in self._children:
            if child.status.state in ("READY", "PENDING"):
                s = child.status.state
                child.status = Status.BROKEN(reason=f"{child}: unexpected status {s}")
            elif child.status.state == "RUNNING":
                child.timekeeper.stop()
                child.status = Status.CANCELLED()
            elif child.status.state not in ("COMPLETE", "NOTRUN"):
                child.status.set(
                    state=state, category=category, status=status, reason=reason, code=code
                )

    def set_base(
        self,
        *,
        state: str | None = None,
        category: str | None = None,
        status: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        """Internal: update only the batch aggregate status."""
        self.base_status.set(
            state=state, category=category, status=status, reason=reason, code=code
        )
