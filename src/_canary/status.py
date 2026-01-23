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
    states: set[str] = {"PENDING", "READY", "RUNNING", "NOTRUN", "COMPLETE"}
    terminal_states = frozenset(("NOTRUN", "COMPLETE"))
    categories: dict[str, tuple[str, ...]] = {
        "PASS": ("SUCCESS", "XDIFF", "XFAIL"),
        "FAIL": ("DIFFED", "FAILED", "ERROR", "BROKEN", "TIMEOUT", "INVALID"),
        "CANCEL": ("CANCELLED", "INTERRUPTED"),
        "SKIP": ("SKIPPED", "BLOCKED"),
        "NONE": ("NONE",),
    }
    categories_for_state: dict[str, set[str]] = {
        "PENDING": {"NONE"},
        "READY": {"NONE"},
        "RUNNING": {"NONE"},
        "NOTRUN": {"SKIP"},
        "COMPLETE": {"PASS", "FAIL", "CANCEL"},
    }
    color_for_category: dict[str, str] = {
        "PASS": "bold green",
        "FAIL": "bold red",
        "SKIP": "yellow",
        "CANCEL": "bold magenta",
        "NONE": "bold",
    }
    html_color_for_category: dict[str, str] = {
        "PASS": "#02FE20",
        "FAIL": "#FF3333",
        "SKIP": "#FEFD02",
        "CANCEL": "#F202FE",
        "NONE": "",
    }  # nosec B105
    code_for_status: dict[str, int] = {
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
    glyph_for_status: dict[str, str] = {
        "PENDING": "○",
        "READY": "○",
        "RUNNING": "▶",
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
        return self.state in self.terminal_states

    @property
    def glyph(self) -> str:
        if self.state in ("PENDING", "READY", "RUNNING"):
            return self.glyph_for_status[self.state]
        return self.glyph_for_status[self.status]

    @property
    def color(self) -> str:
        return self.color_for_category[self.category]

    def set(
        self,
        *,
        state: str | None = None,
        category: str | None = None,
        status: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        if state in ("READY", "PENDING", "RUNNING"):
            category = category or "NONE"
            status = status or "NONE"
        if category == "PASS":
            state = state or "COMPLETE"
            status = status or self.categories[category][0]
        elif category == "FAIL":
            state = state or "COMPLETE"
            status = status or self.categories[category][0]
        elif category == "CANCEL":
            state = state or "COMPLETE"
            status = status or self.categories[category][0]
        elif category == "SKIP":
            state = state or "NOTRUN"
            status = status or self.categories[category][0]
        if status is not None:
            category = category or self._category_from_status(status)
            state = state or self._state_from_category(category)

        if state not in self.states:
            raise ValueError(f"Invalid state: {state}")

        allowed_categories = self.categories_for_state[state]
        if category not in allowed_categories:
            s = ", ".join(allowed_categories)
            raise ValueError(f"Invalid category {category} for state {state}: allowed: {s}")

        allowed_status = self.categories[category]
        if status not in allowed_status:
            s = ", ".join(allowed_status)
            raise ValueError(f"Invalid status {status} for category {category}: allowed: {s}")

        self.state = state
        self.category = category
        self.status = status
        self.reason = reason
        if code < 0:
            code = self.code_for_status.get(self.status, -1)
        self.code = code

    def _category_from_status(self, value: str) -> str:
        for category, statuses in self.categories.items():
            if value in statuses:
                return category
        raise ValueError(f"Invalid status: {value}")

    def _state_from_category(self, value: str) -> str:
        for state, categories in self.categories_for_state.items():
            if value in categories:
                return state
        raise ValueError(f"Invalid category: {value}")

    def display_name(self, **kwargs) -> str:
        style = kwargs.get("style", "none")
        if style == "rich":
            color = self.color_for_category[self.category]
            if self.state == "RUNNING":
                return f"[{color}]{self.state}[/{color}]"
            return f"[{color}]{self.category}[/{color}] ({self.status})"
        elif style == "html":
            color = self.html_color_for_category[self.category]
            if self.state == "RUNNING":
                return f"<font color={color}>{self.state}</font>"
            return f"<font color={color}>{self.category}</font> ({self.status})"
        else:
            return f"{self.category} ({self.status})"

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
        self = cls()
        self.state = data["state"]
        self.category = data["category"]
        self.status = data["status"]
        self.reason = data["reason"]
        self.code = data["code"]
        return self

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
