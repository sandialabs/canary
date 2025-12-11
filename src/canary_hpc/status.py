# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

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

    def display_name(self, **kwargs: Any) -> str:
        return self.base_status.display_name(**kwargs)

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
                    child.status = Status.BROKEN()
                elif child.status.state == "RUNNING":
                    child.timekeeper.stop()
                    child.status = Status.CANCELLED()
                else:
                    child.status.set(
                        state=state, category=category, status=status, reason=reason, code=code
                    )
