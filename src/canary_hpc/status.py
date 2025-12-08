# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

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
    def category(self) -> str:
        return self.base_status.category

    @property
    def cname(self) -> str:
        return self.base_status.cname

    @property
    def color(self) -> str:
        return self.base_status.color

    def asdict(self) -> dict:
        return self.base_status.asdict()

    def set(
        self,
        status: str | int | Status,
        reason: str | None = None,
        code: int | None = None,
        kind: str | None = None,
        propagate: bool = True,
    ) -> None:
        self.base_status.set(status, reason=reason, code=code, kind=kind)
        if propagate:
            for child in self._children:
                if child.status.category in ("READY", "PENDING"):
                    child.status.set("BROKEN")
                elif child.status.category == "RUNNING":
                    child.timekeeper.stop()
                    child.status.set("CANCELLED")
                else:
                    child.status.set(status, reason=reason, code=code, kind=kind)

    @property
    def status(self) -> Status:
        return self.base_status
