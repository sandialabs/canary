# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import signal

from .error import diff_exit_status
from .error import fail_exit_status
from .error import skip_exit_status
from .error import timeout_exit_status
from .third_party.color import colorize
from .util import glyphs


class Status:
    """The status of a ``canary`` test case."""

    members = (
        "created",
        "retry",
        "pending",
        "ready",
        "running",
        "cancelled",
        "not_run",
        "unknown",
        "success",
        "xfail",
        "xdiff",
        "skipped",
        "diffed",
        "failed",
        "timeout",
    )
    colors = {
        "created": "b",
        "retry": "r",
        "pending": "b",
        "ready": "b",
        "running": "c",
        "cancelled": "y",
        "not_run": "R",
        "unknown": "R",
        "success": "G",
        "xfail": "c",
        "xdiff": "c",
        "skipped": "m",
        "diffed": "y",
        "failed": "R",
        "timeout": "R",
    }

    def __init__(self, arg: str = "created", details: str | None = None) -> None:
        self.value: str
        self.details: str | None
        self.set(arg, details)

    def __str__(self):
        return repr(self)

    def __repr__(self):
        string_repr = self.value
        if self.details:
            string_repr += f": {self.details}"
        return string_repr

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return other == self.value
        else:
            assert isinstance(other, Status)
            return self.iid == other.iid

    def __hash__(self) -> int:
        return hash(f"{self.value}%{self.details}")

    def complete(self) -> bool:
        value = self.value
        return value in ("success", "xfail", "xdiff", "skipped", "diffed", "failed", "timeout")

    def ready(self) -> bool:
        return self.value == "ready"

    def pending(self) -> bool:
        return self.value == "pending"

    def satisfies(self, arg: str | tuple[str, ...]) -> bool:
        if isinstance(arg, str):
            arg = (arg,)
        return self.value in arg

    @staticmethod
    def glyph(status):
        map = {
            "created": glyphs.mdash,
            "retry": glyphs.retry,
            "pending": glyphs.mdash,
            "ready": glyphs.mdash,
            "running": glyphs.ellipsis,
            "cancelled": glyphs.ballotx,
            "success": glyphs.checkmark,
            "xfail": glyphs.checkmark,
            "xdiff": glyphs.checkmark,
            "skipped": glyphs.ballotx,
            "diffed": glyphs.ballotx,
            "failed": glyphs.ballotx,
            "timeout": glyphs.ballotx,
            "not_run": glyphs.ballotx,
            "unknown": glyphs.ballotx,
        }
        glyph = map[status]
        color = Status.colors[status]
        return colorize("@*%s{%s}" % (color, glyph))

    def set_from_code(self, arg: int) -> None:
        assert isinstance(arg, int)
        if arg == 0:
            self.set("success")
        elif arg == diff_exit_status:
            self.set("diffed", "the diff exit status was returned")
        elif arg == skip_exit_status:
            self.set("skipped", "the skip exit status was returned")
        elif arg == fail_exit_status:
            self.set("failed", "the fail exit status was returned")
        elif arg == timeout_exit_status:
            self.set("timeout")
        elif abs(arg) == signal.SIGINT.value:
            self.set("cancelled", "keyboard interrupt")
        else:
            self.set("failed", "a non-zero exit status was returned")

    @property
    def name(self) -> str:
        if self.value == "success":
            return "PASS"
        elif self.value == "diffed":
            return "DIFF"
        elif self.value == "failed":
            return "FAIL"
        elif self.value == "not_run":
            return "NOT RUN"
        else:
            return self.value.upper()

    @property
    def cname(self) -> str:
        return colorize("@*%s{%s}" % (self.color, self.name))

    @property
    def color(self) -> str:
        return self.colors[self.value]

    @property
    def iid(self) -> str:
        if self.details:
            return f"{self.value}:{self.details}"
        return self.value

    def set(self, arg: str, details: str | None = None) -> None:
        if arg not in self.members:
            raise ValueError(f"{arg} is not a valid status")
        if arg in ("skipped", "failed", "diffed") and details is None:
            details = "unknown"
        if arg in ("pending", "ready", "created", "retry"):
            if details is not None:
                raise ValueError(f"details not compatible with Status({arg!r})")
        self.value = arg
        self.details = details

    @property
    def html_name(self) -> str:
        color = {
            "r": "#FF3333",
            "b": "#3354FF",
            "m": "#F202FE",
            "g": "#02FE20",
            "y": "#FEFD02",
            "c": "#00FFFF",
        }[self.color.lower()]
        return f"<font color={color}>{self.name}</font>"
