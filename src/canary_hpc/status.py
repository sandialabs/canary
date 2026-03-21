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
        for child in self._children:
            if child.status.category == "PASS":
                counts[(child.status.category, "PASS")] += 1
            else:
                counts[(child.status.category, child.status.status)] += 1
        style = kwargs.get("style")
        parts: list[str] = []
        for cat, stat in sorted(counts, key=sortkey):
            count = counts[(cat, stat)]
            if style == "rich":
                color = self.base_status.color_for_category[cat]
                parts.append(f"{count} [{color}]{stat}[/{color}]")
            elif style == "rich":
                color = self.base_status.color_for_category[cat][0]
                parts.append("%d @%s{%s}" % (count, color, stat))
            else:
                parts.append(f"{count} {stat}")
        return f"{self.base_status.category} ({', '.join(parts)})"

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
        propagate: bool = True,
    ) -> None:
        self.base_status.set(
            state=state, category=category, status=status, reason=reason, code=code
        )
        if propagate:
            for child in self._children:
                if child.status.state in ("READY", "PENDING"):
                    s = child.status.state
                    child.status = Status.BROKEN(reason=f"{child}: unexpected status {s}")
                elif child.status.state == "RUNNING":
                    child.timekeeper.stop()
                    child.status = Status.CANCELLED()
                else:
                    child.status.set(
                        state=state, category=category, status=status, reason=reason, code=code
                    )
