from typing import Optional
from typing import Union

from ..error import diff_exit_status
from ..error import fail_exit_status
from ..error import skip_exit_status
from ..error import timeout_exit_status
from ..third_party.color import colorize


class Status:
    members = (
        "masked",
        "created",
        "pending",
        "ready",
        "running",
        "cancelled",
        "skipped",
        "diffed",
        "failed",
        "timeout",
        "success",
        "xfail",
        "xdiff",
    )
    colors = {
        "masked": "y",
        "created": "b",
        "pending": "b",
        "ready": "b",
        "running": "c",
        "cancelled": "y",
        "skipped": "m",
        "diffed": "y",
        "failed": "R",
        "timeout": "R",
        "success": "G",
        "xfail": "c",
        "xdiff": "c",
    }

    def __init__(self, arg: str = "created", details: Optional[str] = None) -> None:
        self.value: str
        self.details: Union[None, str]
        self.set(arg, details)

    def __str__(self):
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

    def set_from_code(self, arg: int) -> None:
        assert isinstance(arg, int)
        if arg == 0:
            self.set("success")
        elif arg == diff_exit_status:
            self.set("diffed")
        elif arg == skip_exit_status:
            self.set("skipped", "runtime exception")
        elif arg == fail_exit_status:
            self.set("failed")
        elif arg == timeout_exit_status:
            self.set("timeout")
        elif arg == -2:
            self.set("timeout")
        else:
            self.set("failed")

    @property
    def name(self) -> str:
        if self.value == "success":
            return "PASS"
        elif self.value == "diffed":
            return "DIFF"
        elif self.value == "failed":
            return "FAIL"
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

    def set(self, arg: str, details: Optional[str] = None) -> None:
        if arg not in self.members:
            raise ValueError(f"{arg} is not a valid status")
        if arg in ("skipped",):
            if details is None:
                raise ValueError(f"details for status {arg!r} must be provided")
        if arg in ("pending", "ready", "created"):
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
        }[self.color.lower()]
        return f"<font color={color}>{self.name}</font>"
