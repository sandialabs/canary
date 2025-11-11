# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import enum
import signal
from typing import Any

from .error import diff_exit_status
from .error import exception_exit_status
from .error import fail_exit_status
from .error import skip_exit_status
from .error import timeout_exit_status


class StatusColor(str, enum.Enum):
    PENDING = "blue"
    READY = "blue"
    RUNNING = "cyan"
    SUCCESS = "green"
    FAILED = "red"
    DIFFED = "red"
    NOT_RUN = "red"
    SKIPPED = "magenta"
    CANCELLED = "yellow"
    XFAIL = "cyan"
    XDIFF = "cyan"
    TIMEOUT = "red"
    RETRY = "yellow"


class StatusValue(enum.Enum):
    PENDING = enum.auto()
    READY = enum.auto()
    RUNNING = enum.auto()
    SUCCESS = enum.auto()
    FAILED = enum.auto()
    DIFFED = enum.auto()
    NOT_RUN = enum.auto()
    SKIPPED = enum.auto()
    CANCELLED = enum.auto()
    RETRY = enum.auto()
    XFAIL = enum.auto()
    XDIFF = enum.auto()
    TIMEOUT = enum.auto()

    @property
    def color(self) -> StatusColor:
        return {
            StatusValue.PENDING: StatusColor.PENDING,
            StatusValue.READY: StatusColor.READY,
            StatusValue.RUNNING: StatusColor.RUNNING,
            StatusValue.SUCCESS: StatusColor.SUCCESS,
            StatusValue.FAILED: StatusColor.FAILED,
            StatusValue.DIFFED: StatusColor.DIFFED,
            StatusValue.NOT_RUN: StatusColor.NOT_RUN,
            StatusValue.SKIPPED: StatusColor.SKIPPED,
            StatusValue.CANCELLED: StatusColor.CANCELLED,
            StatusValue.RETRY: StatusColor.RETRY,
            StatusValue.XFAIL: StatusColor.XFAIL,
            StatusValue.XDIFF: StatusColor.XDIFF,
            StatusValue.TIMEOUT: StatusColor.TIMEOUT,
        }[self]

    def default_code(self) -> int:
        return {
            StatusValue.PENDING: -1,
            StatusValue.READY: -1,
            StatusValue.RUNNING: -1,
            StatusValue.SUCCESS: 0,
            StatusValue.FAILED: 1,
            StatusValue.DIFFED: diff_exit_status,
            StatusValue.NOT_RUN: 1,
            StatusValue.SKIPPED: skip_exit_status,
            StatusValue.CANCELLED: signal.SIGINT.value,
            StatusValue.RETRY: -1,
            StatusValue.XFAIL: 0,
            StatusValue.XDIFF: 0,
            StatusValue.TIMEOUT: timeout_exit_status,
        }[self]

    @property
    def glyph(self) -> str:
        return {
            StatusValue.PENDING: "—",
            StatusValue.READY: "—",
            StatusValue.RUNNING: "…",
            StatusValue.SUCCESS: "✔",
            StatusValue.FAILED: "✗",
            StatusValue.DIFFED: "✗",
            StatusValue.NOT_RUN: "✗",
            StatusValue.SKIPPED: "✗",
            StatusValue.CANCELLED: "🚫",
            StatusValue.RETRY: "⟳",
            StatusValue.XFAIL: "✔",
            StatusValue.XDIFF: "✔",
            StatusValue.TIMEOUT: "✗",
        }[self]


@dataclasses.dataclass
class Status:
    value: StatusValue = dataclasses.field(default=StatusValue.PENDING)
    details: str | None = None
    code: int = -1

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return other.lower() == self.value.name.lower()
        else:
            assert isinstance(other, Status)
            return self.iid == other.iid

    @property
    def name(self) -> str:
        return self.value.name

    @property
    def color(self) -> str:
        return self.value.color

    @property
    def glyph(self) -> str:
        return self.value.glyph

    @property
    def iid(self) -> str:
        if self.details:
            return f"{self.value.name}:{self.details}"
        return self.value

    def satisfies(self, arg: str | tuple[str, ...]) -> bool:
        if isinstance(arg, str):
            arg = (arg,)
        return self.value.name.lower() in arg

    def set(
        self, arg: str | StatusValue, details: str | None = None, code: str | None = None
    ) -> None:
        if isinstance(arg, str):
            arg = StatusValue[arg.upper()]
        if not isinstance(arg, StatusValue):
            raise ValueError(f"{arg} is not a valid status")
        if arg in (StatusValue.SKIPPED, StatusValue.FAILED, StatusValue.DIFFED) and details is None:
            details = "unknown"
        if arg in (StatusValue.PENDING, StatusValue.READY, StatusValue.RETRY):
            if details is not None:
                raise ValueError(f"details ({details}) not compatible with Status({arg!r})")
        self.value = arg
        self.details = details
        if code is None:
            code = arg.default_code()
        self.code = code

    def set_from_code(self, code: int, details: str | None = None) -> None:
        if code == 0:
            self.set(StatusValue.SUCCESS)
        elif code == diff_exit_status:
            self.set(
                StatusValue.DIFFED,
                details=details or "the diff exit status was returned",
                code=code,
            )
        elif code == skip_exit_status:
            self.set(
                StatusValue.SKIPPED,
                details=details or "the skip exit status was returned",
                code=code,
            )
        elif code == fail_exit_status:
            self.set(
                StatusValue.FAILED,
                details=details or "the fail exit status was returned",
                code=code,
            )
        elif code == timeout_exit_status:
            self.set(StatusValue.TIMEOUT, details=details, code=code)
        elif abs(code) == signal.SIGINT.value:
            self.set(StatusValue.CANCELLED, details="Keyboard interrupt", code=code)
        elif code == exception_exit_status:
            details = details or "Exception occurred during test execution"
            self.set(StatusValue.FAILED, details=details, code=code)
        else:
            self.set(
                StatusValue.FAILED,
                details=details or "a non-zero exit status was returned",
                code=code,
            )

    def asdict(self) -> dict[str, Any]:
        return {"value": self.value.name, "details": self.details, "code": self.code}
