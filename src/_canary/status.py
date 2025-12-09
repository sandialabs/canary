# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


class Status:
    """Lightweight status object for test cases.
    Can be created from either status category or return code.
    JSON serializable via to_dict() and from_dict().

    Examples:
        status = Status('SUCCESS')
        status = Status('SUCCESS', code=42)  # Custom code
        status = Status(0, reason="All tests passed")
        status = Status.SUCCESS("Build completed")

        # JSON serialization
        json_str = json.dumps(status.to_dict())
        status2 = Status.from_dict(json.loads(json_str))
    """

    # Status definitions: (default_code, color, glyph, extra label)
    categories = {
        "PENDING": (-3, "Blue", "○", ()),
        "READY": (-2, "Blue", "○", ()),
        "RUNNING": (-1, "green", "▶", ()),
        "SUCCESS": (0, "Green", "✓", ("PASS",)),
        "XFAIL": (50, "Cyan", "✓", ()),
        "XDIFF": (51, "Cyan", "✓", ()),
        "RETRY": (52, "Yellow", "⟳", ()),
        "BLOCKED": (62, "Magenta", "⊘", ()),
        "SKIPPED": (63, "Magenta", "⊘", ()),
        "DIFFED": (64, "Magenta", "✗", ("DIFF",)),
        "FAILED": (65, "Red", "✗", ("FAIL",)),
        "TIMEOUT": (66, "Red", "⏱", ()),
        "ERROR": (67, "Red", "⚠", ()),
        "BROKEN": (68, "Red", "✗", ()),
        "CANCELLED": (69, "Magenta", "⊘", ()),
    }

    # Reverse mapping: code -> category (for default codes only)
    code2category = {code: category for category, (code, _, _, _) in categories.items()}

    def __init__(
        self,
        status: "str | int | Status" = "PENDING",
        reason: str | None = None,
        code: int | None = None,
        kind: str | None = None,
    ):
        """Create a Status from a category, code, or another Status.

        Args:
            status: Status category (str), return code (int), or Status object
            reason: Optional reason associated with this status
            code: Optional custom return code (overrides default)
        """
        self._category: str
        self._reason: str | None
        self._code: int
        self._kind: str | None
        self.set(status, reason, code, kind)

    def set(
        self,
        status: "str | int | Status" = "PENDING",
        reason: str | None = None,
        code: int | None = None,
        kind: str | None = None,
    ) -> None:
        if isinstance(status, Status):
            self._category = status._category
            self._reason = reason if reason is not None else status._reason
            self._code = code if code is not None else status._code
            self._kind = status._kind
            return
        if isinstance(status, int):
            # Look up by code (only works for default codes)
            if status in self.code2category:
                self._category = self.code2category[status]
            else:
                self._category = "FAILED"
            self._code = code if code is not None else status
        elif isinstance(status, str):
            # Look up by category
            category = status.upper()
            if category not in self.categories:
                raise ValueError(f"Unknown status category: {status}")
            self._category = category
            # Use provided code or default
            default_code = self.categories[category][0]
            self._code = code if code is not None else default_code
            self._kind = kind
        else:
            raise TypeError(f"Status must be str, int, or Status, not {type(status)}")
        self._reason = reason
        self._kind = kind

    @property
    def category(self) -> str:
        """Status category (e.g., 'SUCCESS')."""
        return self._category

    @property
    def kind(self) -> str | None:
        return self._kind

    @property
    def code(self) -> int:
        """Return code (default or custom)."""
        return self._code

    @property
    def reason(self) -> str | None:
        """Optional reason associated with this status."""
        return self._reason

    def display_name(self, **kwargs) -> str:
        name = self._category.replace("_", " ")
        if kwargs.get("rich"):
            tag = self.color.lower()
            if self.color[0].isupper():
                tag = f"bold {tag}"
            return f"[{tag}]{name}[/{tag}]"
        elif kwargs.get("color"):
            return "@*%s{%s}" % (self.color[0], name)
        return name

    @property
    def cname(self) -> str:
        return "@*%s{%s}" % (self.color[0], self.category)

    @property
    def html_name(self) -> str:
        color = {
            "r": "#FF3333",
            "b": "#3354FF",
            "m": "#F202FE",
            "g": "#02FE20",
            "y": "#FEFD02",
            "c": "#00FFFF",
        }[self.color[0].lower()]
        return f"<font color={color}>{self.category}</font>"

    @property
    def color(self) -> str:
        """Associated color (e.g., 'green' for SUCCESS)."""
        return self.categories[self._category][1]

    @property
    def glyph(self) -> str:
        """Associated glyph (e.g., '✓' for SUCCESS)."""
        return self.categories[self._category][2]

    @property
    def labels(self) -> list[str]:
        return list(self.categories[self._category][-1])

    def asdict(self) -> dict:
        """
        Convert Status to a JSON-serializable dictionary.

        Returns:
            Dictionary with category, code, and reason (if present)
        """
        result = {
            "category": self._category,
            "code": self._code,
            "reason": self._reason,
            "kind": self._kind,
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
        return cls(
            status=data["category"],
            code=data["code"],
            reason=data.get("reason"),
            kind=data.get("kind"),
        )

    def __eq__(self, other) -> bool:
        """Compare by category, code, and reason."""
        if isinstance(other, Status):
            return (
                self._category == other._category
                and self._code == other._code
                and self._reason == other._reason
                and self._kind == other._kind
            )
        elif isinstance(other, str):
            # String comparison only checks category, not reason or code
            return self._category == other.upper()
        elif isinstance(other, int):
            # Int comparison only checks code, not category or reason
            return self.code == other
        return False

    def __hash__(self):
        """Allow Status to be used in sets and as dict keys."""
        return hash((self._category, self._code, self._reason, self._kind))

    def __str__(self) -> str:
        """String representation."""
        if self._reason:
            return f"{self._category}: {self._reason}"
        return self._category

    def __repr__(self) -> str:
        """Developer representation."""
        parts = [f"{self._category!r}"]
        if self._reason:
            parts.append(f"reason={self._reason!r}")
        # Show code if it's not the default
        default_code = self.categories[self._category][0]
        if self._code != default_code:
            parts.append(f"code={self._code}")
        return f"Status({', '.join(parts)})"

    def __int__(self) -> int:
        """Convert to int (return code)."""
        return self.code

    # Class-level constants for convenience
    @classmethod
    def PENDING(cls, reason: str | None = None, code: int | None = None):
        return cls("PENDING", reason=reason, code=code)

    @classmethod
    def READY(cls, reason: str | None = None, code: int | None = None):
        return cls("READY", reason=reason, code=code)

    @classmethod
    def RUNNING(cls, reason: str | None = None, code: int | None = None):
        return cls("RUNNING", reason=reason, code=code)

    @classmethod
    def SUCCESS(cls, reason: str | None = None, code: int | None = None):
        return cls("SUCCESS", reason=reason, code=code)

    @classmethod
    def XFAIL(cls, reason: str | None = None, code: int | None = None):
        return cls("XFAIL", reason=reason, code=code)

    @classmethod
    def XDIFF(cls, reason: str | None = None, code: int | None = None):
        return cls("XDIFF", reason=reason, code=code)

    @classmethod
    def SKIPPED(cls, reason: str | None = None, code: int | None = None):
        return cls("SKIPPED", reason=reason, code=code)

    @classmethod
    def BLOCKED(cls, reason: str | None = None, code: int | None = None):
        return cls("BLOCKED", reason=reason, code=code)

    @classmethod
    def FAILED(cls, reason: str | None = None, code: int | None = None):
        return cls("FAILED", reason=reason, code=code)

    @classmethod
    def DIFFED(cls, reason: str | None = None, code: int | None = None):
        return cls("DIFFED", reason=reason, code=code)

    @classmethod
    def TIMEOUT(cls, reason: str | None = None, code: int | None = None):
        return cls("TIMEOUT", reason=reason, code=code)

    @classmethod
    def ERROR(cls, reason: str | None = None, code: int | None = None):
        return cls("ERROR", reason=reason, code=code)

    @classmethod
    def BROKEN(cls, reason: str | None = None, code: int | None = None):
        return cls("BROKEN", reason=reason, code=code)
