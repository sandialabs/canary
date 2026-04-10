# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


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
    STATES: tuple[str, ...] = ("PENDING", "READY", "RUNNING", "NOTRUN", "COMPLETE")
    TERMINAL_STATES: tuple[str, str] = ("NOTRUN", "COMPLETE")
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
    CATEGORY_FOR_STATE: dict[str, set[str]] = {
        "PENDING": {"NONE"},
        "READY": {"NONE"},
        "RUNNING": {"NONE"},
        "NOTRUN": {"SKIP"},
        "COMPLETE": {"PASS", "FAIL", "CANCEL"},
    }
    # Precompute fast lookup: category -> state (unambiguous with your data)
    STATE_FOR_CATEGORY: dict[str, str] = {}
    for state in ("PENDING", "READY", "RUNNING", "NOTRUN", "COMPLETE"):
        for cat in CATEGORY_FOR_STATE[state]:
            STATE_FOR_CATEGORY.setdefault(cat, state)
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
        "NONE": -1,
        "PENDING": -1,
        "READY": -1,
        "RUNNING": -1,
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
    GLYPH_FOR_STATE: dict[str, str] = {"PENDING": "○", "READY": "○", "RUNNING": "▶"}
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

    state: str
    category: str
    status: str
    reason: str | None

    def __init__(
        self,
        *,
        state: str = "PENDING",
        category: str = "NONE",
        status: str = "NONE",
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.set(state=state, category=category, status=status, reason=reason, code=code)

    def __eq__(self, o) -> bool:
        if isinstance(o, Status):
            return self.__hash__() == o.__hash__()
        else:
            if self.state in ("PENDING", "READY", "RUNNING"):
                return self.state == o
            return self.status == o

    def __hash__(self):
        """Allow Status to be used in sets and as dict keys."""
        return hash((self.state, self.category, self.status, self.reason, self.code))

    def __str__(self) -> str:
        """String representation."""
        if self.reason:
            return f"{self.status}: {self.reason}"
        return f"{self.category} ({self.status})"

    def __repr__(self) -> str:
        """Developer representation."""
        parts = [f"{self.status!r}"]
        if self.reason:
            parts.append(f"reason={self.reason!r}")
        # Show code if it's not the default
        return f"Status({', '.join(parts)})"

    def __int__(self) -> int:
        """Convert to int (return code)."""
        return self.code

    def is_terminal(self) -> bool:
        return self.state in self.TERMINAL_STATES

    @property
    def glyph(self) -> str:
        if g := self.GLYPH_FOR_STATE.get(self.state):
            return g
        return self.GLYPH_FOR_STATUS[self.status]

    @property
    def color(self) -> str:
        return self.COLOR_FOR_CATEGORY[self.category]

    def set(self, *, state=None, category=None, status=None, reason=None, code=-1) -> None:
        state_was_provided = state is not None
        category_was_provided = category is not None
        status_was_provided = status is not None
        reason_was_provided = reason is not None

        # Start from current values if present, otherwise defaults
        cur_state = getattr(self, "state", "PENDING")
        cur_category = getattr(self, "category", "NONE")
        cur_status = getattr(self, "status", "NONE")
        cur_reason = getattr(self, "reason", None)

        state = cur_state if state is None else state
        category = cur_category if category is None else category
        status = cur_status if status is None else status
        reason = cur_reason if (reason is None and not reason_was_provided) else reason

        # If caller changes category but doesn't specify status, reset status so we can default it.
        if category_was_provided and not status_was_provided:
            status = "NONE"

        # If caller changes status but doesn't specify category, reset category so we can infer it.
        if status_was_provided and not category_was_provided:
            category = "NONE"

        # 1) Explicit lifecycle states always override category/outcome
        #    (but only if the caller actually passed state=...)
        if state_was_provided and state in {"PENDING", "READY", "RUNNING"}:
            category = "NONE"
            status = "NONE"
            self._validate(state=state, category=category, status=status)
            self.state, self.category, self.status = state, category, status
            self.reason = reason
            self.code = -1 if code < 0 else code
            return

        # 2) Infer category from a concrete outcome
        if status != "NONE":
            try:
                inferred = self.OUTCOME_TO_CATEGORY[status]
            except KeyError as e:
                raise ValueError(f"Invalid outcome/status: {status}") from e

            if category == "NONE":
                category = inferred
            elif category != inferred:
                raise ValueError(f"Status {status} implies category {inferred}, not {category}")

        # 3) Default outcome if category is concrete but status is NONE
        if category != "NONE" and status == "NONE":
            status = self.DEFAULT_OUTCOME_FOR_CATEGORY[category]

        # 4) Infer state from category unless user explicitly set a terminal state
        #    If user gave an incompatible terminal state, treat it as an error.
        inferred_state = self._state_from_category(category)

        if state_was_provided and state in {"NOTRUN", "COMPLETE"}:
            if state != inferred_state:
                raise ValueError(f"Category {category} implies state {inferred_state}, not {state}")
        else:
            state = inferred_state

        # 5) Validate and commit
        self._validate(state=state, category=category, status=status)

        self.state = state
        self.category = category
        self.status = status
        self.reason = reason
        self.code = self.CODE_FOR_OUTCOME.get(status, -1) if code < 0 else code

    def asdict(self) -> dict:
        """
        Convert Status to a JSON-serializable dictionary.

        Returns:
            Dictionary with category, code, and reason (if present)
        """
        result = {
            "state": self.state,
            "category": self.category,
            "status": self.status,
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
            state=data.get("state", "PENDING"),
            category=data.get("category", "NONE"),
            status=data.get("status", "NONE"),
            reason=data.get("reason"),
            code=data.get("code", -1),
        )
        return self

    def _category_from_outcome(self, category: str) -> str:
        if cat := self.OUTCOME_TO_CATEGORY.get(category):
            return cat
        raise ValueError(f"Invalid status: {category}")

    def _state_from_category(self, category: str) -> str:
        # Deterministic: NONE -> PENDING, SKIP -> NOTRUN, PASS/FAIL/CANCEL -> COMPLETE
        if category == "NONE":
            return "PENDING"
        if category == "SKIP":
            return "NOTRUN"
        if category in {"PASS", "FAIL", "CANCEL"}:
            return "COMPLETE"
        raise ValueError(f"Invalid category: {category}")

    def _validate(self, *, state: str, category: str, status: str) -> None:
        if state not in self.STATES:
            raise ValueError(f"Invalid state: {state}")

        allowed_categories = self.CATEGORY_FOR_STATE[state]
        if category not in allowed_categories:
            raise ValueError(
                f"Invalid category {category} for state {state}: allowed: {', '.join(allowed_categories)}"
            )

        allowed_outcomes = self.OUTCOMES_BY_CATEGORY[category]
        if status not in allowed_outcomes:
            raise ValueError(
                f"Invalid status {status} for category {category}: allowed: {', '.join(allowed_outcomes)}"
            )

    def display_name(self, **kwargs) -> str:
        style = kwargs.get("style", "none")
        show_glyph = kwargs.get("glyph", False)

        if self.state in {"PENDING", "READY", "RUNNING"}:
            label = self.state
            color = self.COLOR_FOR_CATEGORY["NONE"]
            html_color = self.HTML_COLOR_FOR_CATEGORY["NONE"]
        else:
            label = f"{self.category} ({self.status})"
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

    # Class-level constants for convenience
    @classmethod
    def PENDING(cls):
        self = cls()
        return self

    @classmethod
    def READY(cls):
        self = cls()
        self.state = "READY"
        return self

    @classmethod
    def RUNNING(cls):
        self = cls()
        self.state = "RUNNING"
        return self

    @classmethod
    def SUCCESS(cls):
        self = cls()
        self.set(state="COMPLETE", category="PASS", status="SUCCESS", code=0)
        return self

    @classmethod
    def XFAIL(cls):
        self = cls()
        self.set(state="COMPLETE", category="PASS", status="XFAIL")
        return self

    @classmethod
    def XDIFF(cls):
        self = cls()
        self.set(state="COMPLETE", category="PASS", status="XDIFF")
        return self

    @classmethod
    def FAILED(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(state="COMPLETE", category="FAIL", status="FAILED", reason=reason, code=code)
        return self

    @classmethod
    def DIFFED(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(state="COMPLETE", category="FAIL", status="DIFFED", reason=reason, code=code)
        return self

    @classmethod
    def TIMEOUT(cls, code: int = -1):
        self = cls()
        self.set(state="COMPLETE", category="FAIL", status="TIMEOUT", code=code)
        return self

    @classmethod
    def ERROR(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(state="COMPLETE", category="FAIL", status="ERROR", code=code)
        return self

    @classmethod
    def BROKEN(cls, reason: str | None = None, code: int = -1):
        self = cls()
        self.set(state="COMPLETE", category="FAIL", status="BROKEN", code=code)
        return self

    @classmethod
    def SKIPPED(cls, reason: str | None = None):
        self = cls()
        self.set(state="NOTRUN", category="SKIP", status="SKIPPED", reason=reason)
        return self

    @classmethod
    def BLOCKED(cls, reason: str | None = None):
        self = cls()
        self.set(state="NOTRUN", category="SKIP", status="BLOCKED", reason=reason)
        return self

    @classmethod
    def CANCELLED(cls, reason: str | None = None):
        self = cls()
        self.set(state="COMPLETE", category="CANCEL", status="CANCELLED", reason=reason)
        return self

    @classmethod
    def INTERRUPTED(cls, reason: str | None = None):
        import signal

        self = cls()
        reason = reason or "Keyboard interrupt"
        self.set(
            state="COMPLETE",
            category="CANCEL",
            status="INTERRUPTED",
            reason=reason,
            code=signal.SIGINT.value,
        )
        return self
