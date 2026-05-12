# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Sequence


class Status:
    """Lightweight status object for test cases.

    Examples:
        status = Status(status='SUCCESS')
        status = Status(status='SUCCESS', code=42)  # Custom code
        status = Status(status='SUCCESS', reason="All tests passed")
        status = Status.SUCCESS()

        # JSON serialization
        json_str = json.dumps(status.to_dict())
        status2 = Status.from_dict(json.loads(json_str))
    """

    # Status definitions: (default_code, color, glyph, extra label)
    CATEGORIES: tuple[str, ...] = ("PASS", "FAIL", "CANCEL", "SKIP", "NONE")
    OUTCOMES_BY_CATEGORY: dict[str, tuple[str, ...]] = {
        "PASS": ("SUCCESS", "XDIFF", "XFAIL"),
        "FAIL": ("DIFFED", "FAILED", "ERROR", "BROKEN", "TIMEOUT", "INVALID"),
        "CANCEL": ("CANCELLED", "INTERRUPTED"),
        "SKIP": ("SKIPPED", "BLOCKED"),
        "NONE": ("NONE",),
    }
    # Precompute fast reverse lookup
    OUTCOME_TO_CATEGORY: dict[str, str] = {
        outcome: cat for cat, outcomes in OUTCOMES_BY_CATEGORY.items() for outcome in outcomes
    }
    DEFAULT_OUTCOME_FOR_CATEGORY = {
        cat: outcomes[0] for cat, outcomes in OUTCOMES_BY_CATEGORY.items()
    }
    COLOR_FOR_CATEGORY: dict[str, str] = {
        "PASS": "bold green",
        "FAIL": "bold red",
        "SKIP": "yellow",
        "CANCEL": "bold magenta",
        "NONE": "bold",
    }  # nosec B105
    HTML_COLOR_FOR_CATEGORY: dict[str, str] = {
        "PASS": "#02FE20",
        "FAIL": "#FF3333",
        "SKIP": "#FEFD02",
        "CANCEL": "#F202FE",
        "NONE": "",
    }  # nosec B105
    CODE_FOR_OUTCOME: dict[str, int] = {
        "SUCCESS": 0,
        "XDIFF": 10,
        "XFAIL": 11,
        "DIFFED": 64,
        "FAILED": 65,
        "ERROR": 66,
        "BROKEN": 67,
        "TIMEOUT": 68,
        "INVALID": 69,
        "CANCELLED": 70,
        "INTERRUPTED": 71,
        "SKIPPED": 80,
        "BLOCKED": 81,
    }
    GLYPH_FOR_STATUS: dict[str, str] = {
        "SUCCESS": "✓",
        "XFAIL": "✓",
        "XDIFF": "✓",
        "DIFFED": "✗",
        "FAILED": "✗",
        "ERROR": "⚠",
        "BROKEN": "✗",
        "TIMEOUT": "⏱",
        "CANCELLED": "⊘",
        "INTERRUPTED": "⊘",
        "SKIPPED": "⊘",
        "BLOCKED": "⊘",
    }

    category: str
    outcome: str
    reason: str | None

    def __init__(
        self,
        *,
        category: str = "NONE",
        outcome: str = "NONE",
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.set(category=category, outcome=outcome, reason=reason, code=code)

    def __eq__(self, o) -> bool:
        if isinstance(o, Status):
            return self.__hash__() == o.__hash__()
        else:
            return self.outcome == o

    def __hash__(self):
        """Allow Status to be used in sets and as dict keys."""
        return hash((self.category, self.outcome, self.reason, self.code))

    def __str__(self) -> str:
        """String representation."""
        if self.reason:
            return f"{self.outcome}: {self.reason}"
        return f"{self.category} ({self.outcome})"

    def __repr__(self) -> str:
        """Developer representation."""
        parts = [f"{self.outcome!r}"]
        if self.reason:
            parts.append(f"reason={self.reason!r}")
        # Show code if it's not the default
        return f"Status({', '.join(parts)})"

    def __int__(self) -> int:
        """Convert to int (return code)."""
        return self.code

    @property
    def glyph(self) -> str:
        return self.GLYPH_FOR_STATUS.get(self.outcome, "")

    @property
    def color(self) -> str:
        return self.COLOR_FOR_CATEGORY[self.category]

    def is_success(self) -> bool:
        return self.category == "PASS"

    def is_failure(self) -> bool:
        return self.category == "FAIL"

    def is_skipped(self) -> bool:
        return self.category == "SKIP"

    def is_cancelled(self) -> bool:
        return self.category == "CANCEL"

    def has_category(self, arg: str) -> bool:
        return self.category == arg

    def category_in(self, arg: Sequence[str]) -> bool:
        return self.category in arg

    def has_outcome(self, arg: str) -> bool:
        return self.outcome == arg

    def outcome_in(self, arg: Sequence[str]) -> bool:
        return self.outcome in arg

    def set(self, *, category=None, outcome=None, reason=None, code=-1) -> None:
        category_was_provided = category is not None
        outcome_was_provided = outcome is not None
        reason_was_provided = reason is not None

        # Start from current values if present, otherwise defaults
        cur_category = getattr(self, "category", "NONE")
        cur_outcome = getattr(self, "outcome", "NONE")
        cur_reason = getattr(self, "reason", None)

        category = cur_category if category is None else category
        outcome = cur_outcome if outcome is None else outcome
        reason = cur_reason if (reason is None and not reason_was_provided) else reason

        # If caller changes category but doesn't specify status, reset outcome so we can default it.
        if category_was_provided and not outcome_was_provided:
            outcome = "NONE"

        # If caller changes outcome but doesn't specify category, reset category so we can infer it.
        if outcome_was_provided and not category_was_provided:
            category = "NONE"

        # 1) Infer category from a concrete outcome
        if outcome != "NONE":
            try:
                inferred = self.OUTCOME_TO_CATEGORY[outcome]
            except KeyError as e:
                raise ValueError(f"Invalid outcome/status: {outcome}") from e

            if category == "NONE":
                category = inferred
            elif category != inferred:
                raise ValueError(f"Status {outcome} implies category {inferred}, not {category}")

        # 2) Default outcome if category is concrete but outcome is NONE
        if category != "NONE" and outcome == "NONE":
            outcome = self.DEFAULT_OUTCOME_FOR_CATEGORY[category]

        # 3) Validate and commit
        self._validate(category=category, outcome=outcome)

        self.category = category
        self.outcome = outcome
        self.reason = reason
        self.code = self.CODE_FOR_OUTCOME.get(outcome, -1) if code < 0 else code

    def asdict(self) -> dict:
        """
        Convert Status to a JSON-serializable dictionary.

        Returns:
            Dictionary with category, code, and reason (if present)
        """
        result = {
            "category": self.category,
            "outcome": self.outcome,
            "reason": self.reason,
            "code": self.code,
        }
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Status":
        """
        Create a Status from a dictionary (e.g., from JSON).

        Args:
            data: Dictionary with 'category', 'code', and optional 'reason'

        Returns:
            Status object
        """
        self = cls(
            category=data.get("category", "NONE"),
            outcome=data.get("outcome", "NONE"),
            reason=data.get("reason"),
            code=data.get("code", -1),
        )
        return self

    def _category_from_outcome(self, category: str) -> str:
        if cat := self.OUTCOME_TO_CATEGORY.get(category):
            return cat
        raise ValueError(f"Invalid outcome: {category}")

    def _validate(self, *, category: str, outcome: str) -> None:
        if category not in self.CATEGORIES:
            raise ValueError(f"Invalid {category=}")
        allowed_outcomes = self.OUTCOMES_BY_CATEGORY[category]
        if outcome not in allowed_outcomes:
            raise ValueError(
                f"Invalid {outcome=} for category {category}: allowed: {', '.join(allowed_outcomes)}"
            )

    def display_name(self, **kwargs) -> str:
        style = kwargs.get("style", "none")
        show_glyph = kwargs.get("glyph", False)

        label = f"{self.category} ({self.outcome})"
        color = self.COLOR_FOR_CATEGORY[self.category]
        html_color = self.HTML_COLOR_FOR_CATEGORY[self.category]

        if show_glyph:
            label = f"{self.glyph} {label}"

        if style == "rich":
            return f"[{color}]{label}[/{color}]"
        if style == "html":
            if html_color:
                return f'<font color="{html_color}">{label}</font>'
            return label
        return label

    @classmethod
    def SUCCESS(cls):
        self = cls()
        self.set(category="PASS", outcome="SUCCESS", code=0)
        return self

    @classmethod
    def XFAIL(cls):
        self = cls()
        self.set(category="PASS", outcome="XFAIL")
        return self

    @classmethod
    def XDIFF(cls):
        self = cls()
        self.set(category="PASS", outcome="XDIFF")
        return self

    @classmethod
    def FAILED(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(category="FAIL", outcome="FAILED", reason=reason, code=code)
        return self

    @classmethod
    def DIFFED(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(category="FAIL", outcome="DIFFED", reason=reason, code=code)
        return self

    @classmethod
    def TIMEOUT(cls, code: int = -1):
        self = cls()
        self.set(category="FAIL", outcome="TIMEOUT", code=code)
        return self

    @classmethod
    def ERROR(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(category="FAIL", outcome="ERROR", code=code)
        return self

    @classmethod
    def BROKEN(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(category="FAIL", outcome="BROKEN", code=code)
        return self

    @classmethod
    def SKIPPED(cls, reason: str | None = None):
        self = cls()
        self.set(category="SKIP", outcome="SKIPPED", reason=reason)
        return self

    @classmethod
    def BLOCKED(cls, reason: str | None = None):
        self = cls()
        self.set(category="SKIP", outcome="BLOCKED", reason=reason)
        return self

    @classmethod
    def CANCELLED(cls, reason: str | None = None):
        self = cls()
        self.set(category="CANCEL", outcome="CANCELLED", reason=reason)
        return self

    @classmethod
    def INTERRUPTED(cls, reason: str | None = None):
        import signal

        self = cls()
        reason = reason or "Keyboard interrupt"
        self.set(category="CANCEL", outcome="INTERRUPTED", reason=reason, code=signal.SIGINT.value)
        return self
