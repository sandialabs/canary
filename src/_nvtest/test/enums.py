from typing import Optional
from typing import Union

from ..error import diff_exit_status
from ..error import fail_exit_status
from ..error import skip_exit_status
from ..error import timeout_exit_status
from ..util.tty.color import colorize


class Skip:
    UNREACHABLE = "==UNREACHABLE=="

    def __init__(self, reason: Optional[str] = None) -> None:
        self._reason = reason

    def __bool__(self) -> bool:
        return bool(self.reason)

    def __str__(self) -> str:
        return f"Skip({False if not self.reason else self.reason})"

    @property
    def reason(self) -> str:
        return self._reason or ""

    @reason.setter
    def reason(self, arg: Union[str, bool]) -> None:
        if arg is False:
            self._reason = None
        elif arg is True:
            self._reason = "Skip set to True (no reason given)"
        else:
            self._reason = arg


class Result:
    members = ("NOTRUN", "NOTDONE", "SKIP", "PASS", "DIFF", "FAIL", "TIMEOUT", "SETUP")
    NOTRUN = "NOTRUN"
    NOTDONE = "NOTDONE"
    SKIP = "SKIP"
    PASS = "PASS"
    DIFF = "DIFF"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    SETUP = "SETUP"
    colors = {
        "NOTDONE": "r",
        "NOTRUN": "b",
        "SKIP": "m",
        "PASS": "g",
        "DIFF": "y",
        "FAIL": "R",
        "TIMEOUT": "r",
        "SETUP": "b",
    }

    def __init__(self, arg: str = "", reason: str = "") -> None:
        self.name: str = self.parse(arg)
        self.reason: str = reason

    def __repr__(self) -> str:
        a = [self.name, self.reason]
        return f"Result({', '.join(_ for _ in a if _.split())})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Result):
            return self.__hash__() == other.__hash__()
        assert isinstance(other, str)
        return self.name == other.upper()

    def __hash__(self):
        return hash(f"{self.name}%{self.reason}")

    def parse(self, arg: str) -> str:
        assert isinstance(arg, str)
        if not arg:
            return "NOTDONE"
        for member in self.members:
            if arg.upper() == member:
                return member
        raise ValueError(f"expected result name, got {arg!r}")

    @classmethod
    def from_returncode(cls, arg: int) -> "Result":
        assert isinstance(arg, int)
        if arg == 0:
            return cls("PASS")
        elif arg == diff_exit_status:
            return cls("DIFF")
        elif arg == skip_exit_status:
            return cls("SKIP")
        elif arg == fail_exit_status:
            return cls("FAIL")
        elif arg == timeout_exit_status:
            return cls("TIMEOUT")
        return cls("FAIL")

    @property
    def cname(self) -> str:
        return colorize("@*%s{%s}" % (self.color, self.name))

    @property
    def color(self) -> str:
        return self.colors[self.name]

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
