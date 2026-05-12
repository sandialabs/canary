# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Any
from typing import Protocol

if TYPE_CHECKING:
    pass


class StatusProtocol(Protocol):
    category: str
    outcome: str
    reason: str | None
    code: int
    color: str

    def set(
        self,
        category: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        code: int | None = None,
    ) -> None: ...

    def display_name(self, **kwargs: Any) -> str: ...
