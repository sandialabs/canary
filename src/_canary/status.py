# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


class Status:
    """Lightweight status object for test cases.
    Can be created from either status name or return code.
    JSON serializable via to_dict() and from_dict().

    Examples:
        status = Status('SUCCESS')
        status = Status('SUCCESS', code=42)  # Custom code
        status = Status(0, message="All tests passed")
        status = Status.SUCCESS("Build completed")

        # JSON serialization
        json_str = json.dumps(status.to_dict())
        status2 = Status.from_dict(json.loads(json_str))
    """

    # Status definitions: (default_code, color, glyph, extra label)
    defaults = {
        "PENDING": (-3, "Blue", "○", ()),
        "READY": (-2, "Blue", "○", ()),
        "RUNNING": (-1, "green", "▶", ()),
        "SUCCESS": (0, "Green", "✓", ("PASS",)),
        "XFAIL": (50, "Cyan", "✓", ()),
        "XDIFF": (51, "Cyan", "✓", ()),
        "RETRY": (52, "Yellow", "⟳", ()),
        "SKIPPED": (53, "Magenta", "⊘", ()),
        "CANCELLED": (63, "Magenta", "⊘", ()),
        "DIFFED": (64, "Magenta", "✗", ("DIFF",)),
        "FAILED": (65, "Red", "✗", ("FAIL",)),
        "TIMEOUT": (66, "Red", "⏱", ()),
        "ERROR": (67, "Red", "⚠", ()),
        "NOT_RUN": (68, "Red", "✗", ()),
    }

    # Reverse mapping: code -> name (for default codes only)
    code2name = {code: name for name, (code, _, _, _) in defaults.items()}

    def __init__(
        self,
        status: "str | int | Status" = "PENDING",
        message: str | None = None,
        code: int | None = None,
    ):
        """Create a Status from a name, code, or another Status.

        Args:
            status: Status name (str), return code (int), or Status object
            message: Optional message associated with this status
            code: Optional custom return code (overrides default)
        """
        self._name: str
        self._message: str | None
        self._code: int
        self.set(status, message, code)

    def set(
        self,
        status: "str | int | Status" = "PENDING",
        message: str | None = None,
        code: int | None = None,
    ) -> None:
        if isinstance(status, Status):
            self._name = status._name
            self._message = message if message is not None else status._message
            self._code = code if code is not None else status._code
            return
        if isinstance(status, int):
            # Look up by code (only works for default codes)
            if status in self.code2name:
                self._name = self.code2name[status]
            else:
                self._name = "FAILED"
            self._code = code if code is not None else status
        elif isinstance(status, str):
            # Look up by name
            name = status.upper()
            if name not in self.defaults:
                raise ValueError(f"Unknown status name: {status}")
            self._name = name
            # Use provided code or default
            default_code = self.defaults[name][0]
            self._code = code if code is not None else default_code
        else:
            raise TypeError(f"Status must be str, int, or Status, not {type(status)}")
        self._message = message

    @property
    def name(self) -> str:
        """Status name (e.g., 'SUCCESS')."""
        return self._name

    @property
    def cname(self) -> str:
        return "@*%s{%s}" % (self.color[0], self.name)

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
        return f"<font color={color}>{self.name}</font>"

    @property
    def code(self) -> int:
        """Return code (default or custom)."""
        return self._code

    @property
    def color(self) -> str:
        """Associated color (e.g., 'green' for SUCCESS)."""
        return self.defaults[self._name][1]

    @property
    def glyph(self) -> str:
        """Associated glyph (e.g., '✓' for SUCCESS)."""
        return self.defaults[self._name][2]

    @property
    def message(self) -> str | None:
        """Optional message associated with this status."""
        return self._message

    @property
    def labels(self) -> list[str]:
        return list(self.defaults[self._name][-1])

    def asdict(self) -> dict:
        """
        Convert Status to a JSON-serializable dictionary.

        Returns:
            Dictionary with name, code, and message (if present)
        """
        result = {"name": self._name, "code": self._code, "message": self._message}
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Status":
        """
        Create a Status from a dictionary (e.g., from JSON).

        Args:
            data: Dictionary with 'name', 'code', and optional 'message'

        Returns:
            Status object
        """
        return cls(status=data["name"], code=data["code"], message=data.get("message"))

    def __eq__(self, other) -> bool:
        """Compare by name, code, and message."""
        if isinstance(other, Status):
            return (
                self._name == other._name
                and self._code == other._code
                and self._message == other._message
            )
        elif isinstance(other, str):
            # String comparison only checks name, not message or code
            return self._name == other.upper()
        elif isinstance(other, int):
            # Int comparison only checks code, not name or message
            return self.code == other
        return False

    def __hash__(self):
        """Allow Status to be used in sets and as dict keys."""
        return hash((self._name, self._code, self._message))

    def __str__(self) -> str:
        """String representation."""
        if self._message:
            return f"{self._name}: {self._message}"
        return self._name

    def __repr__(self) -> str:
        """Developer representation."""
        parts = [f"{self._name!r}"]
        if self._message:
            parts.append(f"message={self._message!r}")
        # Show code if it's not the default
        default_code = self.defaults[self._name][0]
        if self._code != default_code:
            parts.append(f"code={self._code}")
        return f"Status({', '.join(parts)})"

    def __int__(self) -> int:
        """Convert to int (return code)."""
        return self.code

    # Class-level constants for convenience
    @classmethod
    def PENDING(cls, message: str | None = None, code: int | None = None):
        return cls("PENDING", message=message, code=code)

    @classmethod
    def READY(cls, message: str | None = None, code: int | None = None):
        return cls("READY", message=message, code=code)

    @classmethod
    def RUNNING(cls, message: str | None = None, code: int | None = None):
        return cls("RUNNING", message=message, code=code)

    @classmethod
    def SUCCESS(cls, message: str | None = None, code: int | None = None):
        return cls("SUCCESS", message=message, code=code)

    @classmethod
    def XFAIL(cls, message: str | None = None, code: int | None = None):
        return cls("XFAIL", message=message, code=code)

    @classmethod
    def XDIFF(cls, message: str | None = None, code: int | None = None):
        return cls("XDIFF", message=message, code=code)

    @classmethod
    def SKIPPED(cls, message: str | None = None, code: int | None = None):
        return cls("SKIPPED", message=message, code=code)

    @classmethod
    def FAILED(cls, message: str | None = None, code: int | None = None):
        return cls("FAILED", message=message, code=code)

    @classmethod
    def DIFFED(cls, message: str | None = None, code: int | None = None):
        return cls("DIFFED", message=message, code=code)

    @classmethod
    def TIMEOUT(cls, message: str | None = None, code: int | None = None):
        return cls("TIMEOUT", message=message, code=code)

    @classmethod
    def ERROR(cls, message: str | None = None, code: int | None = None):
        return cls("ERROR", message=message, code=code)

    @classmethod
    def NOT_RUN(cls, message: str | None = None, code: int | None = None):
        return cls("NOT_RUN", message=message, code=code)
