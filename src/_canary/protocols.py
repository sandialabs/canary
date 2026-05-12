# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Any
from typing import Protocol

if TYPE_CHECKING:
    pass


class StatusProtocol(Protocol):
    state: str
    category: str
    status: str
    reason: str | None
    code: int
    color: str

    def set(
        self,
        state: str | None = None,
        category: str | None = None,
        status: str | None = None,
        reason: str | None = None,
        code: int | None = None,
    ) -> None: ...

    def display_name(self, **kwargs: Any) -> str: ...

    def is_terminal(self) -> bool: ...
