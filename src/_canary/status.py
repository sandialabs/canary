# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from enum import Enum
from enum import IntEnum
from typing import Any
from typing import Literal
from typing import MutableMapping


class Category(str, Enum):
    PASS = "PASS"  # nosec B105
    FAIL = "FAIL"
    CANCEL = "CANCEL"
    SKIP = "SKIP"
    NONE = "NONE"

    def __serialize__(self) -> dict[str, Any]:
        return {"value": self.value}

    @classmethod
    def __deserialize__(cls, d: dict) -> "Category":
        return cls(d["value"])

    @classmethod
    def factory(cls, arg: "Category | str") -> "Category":
        return arg if isinstance(arg, Category) else Category(arg.upper())

    def rich_color(self) -> str:
        if self == Category.PASS:
            return "bold green"
        elif self == Category.FAIL:
            return "bold red"
        elif self == Category.SKIP:
            return "bold yellow"
        elif self == Category.CANCEL:
            return "bold magenta"
        else:
            return "bold"

    def hex_color(self) -> str:
        if self == Category.PASS:
            return "#02FE20"
        elif self == Category.FAIL:
            return "#FF3333"
        elif self == Category.SKIP:
            return "#FEFD02"
        elif self == Category.CANCEL:
            return "#F202FE"
        else:
            return ""


class Outcome(IntEnum):
    NONE = -1
    SUCCESS = 0
    XDIFF = 10
    XFAIL = 11
    DIFFED = 64
    FAILED = 65
    ERROR = 66
    BROKEN = 67
    TIMEOUT = 68
    INVALID = 69
    CANCELLED = 70
    INTERRUPTED = 71
    SKIPPED = 80
    BLOCKED = 81

    def __serialize__(self) -> dict[str, Any]:
        return {"value": self.value}

    @classmethod
    def __deserialize__(cls, d: dict) -> "Outcome":
        return cls(d["value"])

    @property
    def label(self) -> str:
        return self.name

    @classmethod
    def factory(cls, arg: "Outcome | str | int") -> "Outcome":
        if isinstance(arg, Outcome):
            return arg
        if isinstance(arg, int):
            return Outcome(arg)
        s = arg.strip()
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return Outcome(int(s))
        return Outcome[s]

    def glyph(self) -> str:
        return {
            Outcome.SUCCESS: "✓",
            Outcome.XFAIL: "✓",
            Outcome.XDIFF: "✓",
            Outcome.DIFFED: "✗",
            Outcome.FAILED: "✗",
            Outcome.ERROR: "⚠",
            Outcome.BROKEN: "✗",
            Outcome.TIMEOUT: "⏱",
            Outcome.CANCELLED: "⊘",
            Outcome.INTERRUPTED: "⊘",
            Outcome.SKIPPED: "⊘",
            Outcome.BLOCKED: "⊘",
            Outcome.INVALID: "✗",
            Outcome.NONE: "",
        }.get(self, "")


@dataclass(slots=True)
class Status:
    category: Category = Category.NONE
    outcome: Outcome = Outcome.NONE
    reason: str | None = None
    code: int = -1

    def __post_init__(self) -> None:
        self.set(category=self.category, outcome=self.outcome, reason=self.reason, code=self.code)

    def __serialize__(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "outcome": self.outcome,
            "reason": self.reason,
            "code": self.code,
        }

    @classmethod
    def __deserialize__(cls, d: dict) -> "Status":
        return cls(**d)

    # --- Category query methods
    def is_success(self) -> bool:
        return self.category == Category.PASS

    def is_failure(self) -> bool:
        return self.category == Category.FAIL

    def is_skipped(self) -> bool:
        return self.category == Category.SKIP

    def is_cancelled(self) -> bool:
        return self.category == Category.CANCEL

    def is_unset(self) -> bool:
        return self.category == Category.NONE

    def is_terminal(self) -> bool:
        return self.category != Category.NONE

    # --- Outcome query methods
    def is_diffed(self) -> bool:
        return self.outcome == Outcome.DIFFED

    def is_failed(self) -> bool:
        return self.outcome == Outcome.FAILED

    def is_error(self) -> bool:
        return self.outcome == Outcome.ERROR

    def is_timeout(self) -> bool:
        return self.outcome == Outcome.TIMEOUT

    def is_xfail(self) -> bool:
        return self.outcome == Outcome.XFAIL

    def is_xdiff(self) -> bool:
        return self.outcome == Outcome.XDIFF

    def has_code(self, arg: int) -> bool:
        return self.code == arg

    @property
    def returncode(self) -> int:
        return self.code

    def set(
        self,
        *,
        category: Category | str | None = None,
        outcome: Outcome | str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        category_was_provided = category is not None
        outcome_was_provided = outcome is not None
        reason_was_provided = reason is not None

        category2 = self.category if category is None else Category.factory(category)
        outcome2 = self.outcome if outcome is None else Outcome.factory(outcome)
        reason2 = self.reason if (reason is None and not reason_was_provided) else reason

        if category_was_provided and not outcome_was_provided:
            outcome2 = Outcome.NONE
        if outcome_was_provided and not category_was_provided:
            category2 = Category.NONE
        if outcome2 != Outcome.NONE:
            inferred = get_category(outcome2)
            if category2 == Category.NONE:
                category2 = inferred
            elif category2 != inferred:
                raise ValueError(
                    f"Outcome {outcome2.name} implies category {inferred.value}, not {category2.value}"
                )

        if category2 != Category.NONE and outcome2 == Outcome.NONE:
            outcome2 = get_default_outcome(category2)

        allowed = get_possible_outcomes(category2)
        if outcome2 not in allowed:
            raise ValueError(f"Invalid outcome={outcome2.name} for category={category2.value}")

        self.category = category2
        self.outcome = outcome2
        self.reason = reason2
        self.code = outcome2.value if code < 0 else code

    @classmethod
    def from_dict(cls, data: MutableMapping[str, Any]) -> "Status":
        d = dict(data)
        category = d.pop("category", "NONE")
        outcome = d.pop("outcome", None) or d.pop("status", None) or "NONE"
        reason = d.pop("reason", None)
        code = d.pop("code", -1)
        if d:
            raise TypeError(f"Unknown kwargs: {', '.join(d.keys())}")
        self = cls()
        self.set(category=category, outcome=outcome, reason=reason, code=code)
        return self

    def display_name(
        self, *, style: Literal["none", "rich", "html"] = "none", glyph: bool = False
    ) -> str:
        label = f"{self.category.value} ({self.outcome.name})"
        if glyph:
            label = f"{self.glyph()} {label}"
        if style == "rich":
            return f"[{self.rich_color()}]{label}[/]"
        if style == "html":
            c = self.hex_color()
            return f'<font color="{c}">{label}</font>' if c else label
        return label

    def rich_color(self) -> str:
        return self.category.rich_color()

    def hex_color(self) -> str:
        return self.category.hex_color()

    def glyph(self) -> str:
        return self.outcome.glyph()

    @classmethod
    def SUCCESS(cls):
        self = cls()
        self.set(outcome=Outcome.SUCCESS, code=0)
        return self

    @classmethod
    def XFAIL(cls):
        self = cls()
        self.set(outcome=Outcome.XFAIL)
        return self

    @classmethod
    def XDIFF(cls):
        self = cls()
        self.set(outcome=Outcome.XDIFF)
        return self

    @classmethod
    def FAILED(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(outcome=Outcome.FAILED, reason=reason, code=code)
        return self

    @classmethod
    def DIFFED(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(outcome=Outcome.DIFFED, reason=reason, code=code)
        return self

    @classmethod
    def TIMEOUT(cls, code: int = -1):
        self = cls()
        self.set(outcome=Outcome.TIMEOUT, code=code)
        return self

    @classmethod
    def ERROR(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(outcome=Outcome.ERROR, reason=reason, code=code)
        return self

    @classmethod
    def BROKEN(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(outcome=Outcome.BROKEN, reason=reason, code=code)
        return self

    @classmethod
    def SKIPPED(cls, reason: str | None = None):
        self = cls()
        self.set(outcome=Outcome.SKIPPED, reason=reason)
        return self

    @classmethod
    def BLOCKED(cls, reason: str | None = None):
        self = cls()
        self.set(outcome=Outcome.BLOCKED, reason=reason)
        return self

    @classmethod
    def CANCELLED(cls, reason: str | None = None):
        self = cls()
        self.set(outcome=Outcome.CANCELLED, reason=reason)
        return self

    @classmethod
    def INTERRUPTED(cls, reason: str | None = None):
        import signal

        self = cls()
        reason = reason or "Keyboard interrupt"
        self.set(outcome=Outcome.INTERRUPTED, reason=reason, code=signal.SIGINT.value)
        return self


def get_category(arg: Outcome) -> "Category":
    if arg in (Outcome.SUCCESS, Outcome.XDIFF, Outcome.XFAIL):
        return Category.PASS
    elif arg in (
        Outcome.DIFFED,
        Outcome.FAILED,
        Outcome.ERROR,
        Outcome.BROKEN,
        Outcome.TIMEOUT,
        Outcome.INVALID,
    ):
        return Category.FAIL
    elif arg in (Outcome.CANCELLED, Outcome.INTERRUPTED):
        return Category.CANCEL
    elif arg in (Outcome.SKIPPED, Outcome.BLOCKED):
        return Category.SKIP
    else:
        return Category.NONE


def get_possible_outcomes(arg: Category) -> tuple["Outcome", ...]:
    if arg == Category.PASS:
        return (Outcome.SUCCESS, Outcome.XDIFF, Outcome.XFAIL)
    elif arg == Category.FAIL:
        return (
            Outcome.DIFFED,
            Outcome.FAILED,
            Outcome.ERROR,
            Outcome.BROKEN,
            Outcome.TIMEOUT,
            Outcome.INVALID,
        )
    elif arg == Category.CANCEL:
        return (Outcome.CANCELLED, Outcome.INTERRUPTED)
    elif arg == Category.SKIP:
        return (Outcome.SKIPPED, Outcome.BLOCKED)
    else:
        return (Outcome.NONE,)


def get_default_outcome(arg: Category) -> "Outcome":
    if arg == Category.PASS:
        return Outcome.SUCCESS
    elif arg == Category.FAIL:
        return Outcome.DIFFED
    elif arg == Category.CANCEL:
        return Outcome.CANCELLED
    elif arg == Category.SKIP:
        return Outcome.SKIPPED
    else:
        return Outcome.NONE
