# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Job result status model: categories, outcomes, and the composite Status object.

Three concepts are defined here:

* :class:`Category` — broad pass/fail bucket (PASS, FAIL, CANCEL, SKIP, NONE).
* :class:`Outcome` — specific result code within a category (FAILED, TIMEOUT,
  BLOCKED, SUCCESS, …).
* :class:`Status` — composite object holding (category, outcome, reason, exit code).
  The ``set()`` method enforces the invariant that outcome and category are always
  consistent; it infers one from the other when only one is supplied.

Helper functions at module level:

* :func:`get_category` — map an ``Outcome`` to its ``Category``.
* :func:`get_possible_outcomes` — enumerate valid ``Outcome`` values for a ``Category``.
* :func:`get_default_outcome` — return the canonical default ``Outcome`` for a ``Category``.
"""

from dataclasses import dataclass
from enum import Enum
from enum import IntEnum
from typing import Any
from typing import Literal
from typing import MutableMapping


class Category(str, Enum):
    """Broad result bucket for a finished job.

    Categories group related outcomes for high-level filtering and reporting.
    Use :func:`get_category` to derive the ``Category`` for a specific
    :class:`Outcome`.

    Attributes:
        PASS: The job succeeded (possibly as an expected failure/diff).
        FAIL: The job produced an unacceptable result.
        CANCEL: The job was cancelled or interrupted before completion.
        SKIP: The job was skipped or blocked by a dependency.
        NONE: No result has been recorded yet (initial/unset state).
    """

    PASS = "PASS"  # nosec B105
    FAIL = "FAIL"
    CANCEL = "CANCEL"
    SKIP = "SKIP"
    NONE = "NONE"

    def __serialize__(self) -> str:
        """Serialize to the enum's string value (e.g. ``'PASS'``)."""
        return self.value

    @classmethod
    def __deserialize__(cls, d: "dict | str") -> "Category":
        """Deserialize from a plain string or a legacy ``{"value": ...}`` dict."""
        if isinstance(d, str):
            return cls(d)
        return cls(d["value"])

    @classmethod
    def factory(cls, arg: "Category | str") -> "Category":
        """Coerce a string or ``Category`` to a ``Category``, uppercasing as needed."""
        return arg if isinstance(arg, Category) else Category(arg.upper())

    def rich_color(self) -> str:
        """Return a Rich markup color string for this category."""
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
        """Return an HTML hex color string for this category (empty string if NONE)."""
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
    """Specific result code for a finished job.

    Each outcome belongs to exactly one :class:`Category`; use
    :func:`get_category` to retrieve it.  Integer values are stable across
    releases and are used as process exit codes and database storage keys.

    Attributes:
        NONE: No result recorded (initial state, value ``-1``).
        SUCCESS: Job passed cleanly (exit 0).
        XDIFF: Expected diff — diff result that was anticipated (counts as PASS).
        XFAIL: Expected failure — fail result that was anticipated (counts as PASS).
        DIFFED: Output differed from baseline (FAIL category).
        FAILED: Explicit test failure (non-zero exit, FAIL category).
        ERROR: Framework-level error running the job (FAIL category).
        BROKEN: Internal error; job state is inconsistent (FAIL category).
        TIMEOUT: Job exceeded its allotted wall-clock budget (FAIL category).
        INVALID: Job specification is invalid and could not be run (FAIL category).
        CANCELLED: Job was explicitly cancelled by the user (CANCEL category).
        INTERRUPTED: Job was interrupted by a signal (CANCEL category).
        SKIPPED: Job was filtered out before execution (SKIP category).
        BLOCKED: Job cannot run because an upstream dependency did not satisfy
            its run condition (SKIP category).
    """

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

    def __serialize__(self) -> str:
        """Serialize to the outcome name (e.g. ``'FAILED'``)."""
        return self.name

    @classmethod
    def __deserialize__(cls, d: "dict | str | int") -> "Outcome":
        """Deserialize from a name string, integer, or legacy ``{"value": N}`` dict."""
        if isinstance(d, str):
            # Accept both name ("FAILED") and legacy int-string ("65")
            if d.isdigit() or (d.startswith("-") and d[1:].isdigit()):
                return cls(int(d))
            return cls[d]
        if isinstance(d, int):
            return cls(d)
        return cls(d["value"])

    @property
    def label(self) -> str:
        """Human-readable label; identical to the enum name."""
        return self.name

    @classmethod
    def factory(cls, arg: "Outcome | str | int") -> "Outcome":
        """Coerce a string name, integer value, or ``Outcome`` to an ``Outcome``."""
        if isinstance(arg, Outcome):
            return arg
        if isinstance(arg, int):
            return Outcome(arg)
        s = arg.strip()
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return Outcome(int(s))
        return Outcome[s]

    def glyph(self) -> str:
        """Return a single Unicode glyph representing this outcome (e.g. ✓, ✗, ⏱)."""
        return {
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
    """Composite result descriptor for a single job execution.

    Stores the :class:`Category`, specific :class:`Outcome`, an optional
    human-readable ``reason`` string, and a numeric ``code`` (usually the
    process exit code or the outcome's integer value).

    The :meth:`set` method is the primary mutator.  It enforces consistency
    between ``category`` and ``outcome``: supplying one automatically infers
    the other, and supplying both raises ``ValueError`` if they conflict.

    Convenience class-method constructors (e.g. :meth:`SUCCESS`, :meth:`FAILED`,
    :meth:`TIMEOUT`) create pre-filled ``Status`` objects for common outcomes.

    Attributes:
        category: Broad result bucket.
        outcome: Specific result code.
        reason: Optional free-text explanation (timeout message, diff summary, …).
        code: Numeric exit code; defaults to the outcome's integer value.
    """

    category: Category = Category.NONE
    outcome: Outcome = Outcome.NONE
    reason: str | None = None
    code: int = -1

    def __post_init__(self) -> None:
        """Validate and normalise the initial field values via :meth:`set`."""
        self.set(category=self.category, outcome=self.outcome, reason=self.reason, code=self.code)

    def __serialize__(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict with serializable category/outcome values."""
        return {
            "category": self.category,
            "outcome": self.outcome,
            "reason": self.reason,
            "code": self.code,
        }

    @classmethod
    def __deserialize__(cls, d: dict) -> "Status":
        """Reconstruct a ``Status`` from a serialized dict."""
        return cls(**d)

    def reset(self) -> None:
        """Reset all fields to their unset defaults."""
        self.category = Category.NONE
        self.outcome = Outcome.NONE
        self.reason = None
        self.code = -1

    # --- Category query methods
    def is_success(self) -> bool:
        """True if the job passed (category is PASS)."""
        return self.category == Category.PASS

    def is_failure(self) -> bool:
        """True if the job failed (category is FAIL)."""
        return self.category == Category.FAIL

    def is_skipped(self) -> bool:
        """True if the job was skipped or blocked (category is SKIP)."""
        return self.category == Category.SKIP

    def is_cancelled(self) -> bool:
        """True if the job was cancelled or interrupted (category is CANCEL)."""
        return self.category == Category.CANCEL

    def is_unset(self) -> bool:
        """True if no result has been recorded yet (category is NONE)."""
        return self.category == Category.NONE

    def is_terminal(self) -> bool:
        """True if a final result has been recorded (category is not NONE)."""
        return self.category != Category.NONE

    # --- Outcome query methods
    def is_blocked(self) -> bool:
        """True if the outcome is BLOCKED (upstream dependency not satisfied)."""
        return self.outcome == Outcome.BLOCKED

    def is_diffed(self) -> bool:
        """True if the outcome is DIFFED (output differed from baseline)."""
        return self.outcome == Outcome.DIFFED

    def is_failed(self) -> bool:
        """True if the outcome is FAILED (explicit test failure)."""
        return self.outcome == Outcome.FAILED

    def is_error(self) -> bool:
        """True if the outcome is ERROR (framework-level error)."""
        return self.outcome == Outcome.ERROR

    def is_timeout(self) -> bool:
        """True if the outcome is TIMEOUT (job exceeded its wall-clock budget)."""
        return self.outcome == Outcome.TIMEOUT

    def is_xfail(self) -> bool:
        """True if the outcome is XFAIL (expected failure, counts as PASS)."""
        return self.outcome == Outcome.XFAIL

    def is_xdiff(self) -> bool:
        """True if the outcome is XDIFF (expected diff, counts as PASS)."""
        return self.outcome == Outcome.XDIFF

    def has_code(self, arg: int) -> bool:
        """True if the numeric exit code matches ``arg``."""
        return self.code == arg

    @property
    def returncode(self) -> int:
        """Alias for :attr:`code`; the numeric process exit code."""
        return self.code

    def set(
        self,
        *,
        category: Category | str | None = None,
        outcome: Outcome | str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        """Atomically update this status, enforcing category/outcome consistency.

        Rules:
        - If only ``outcome`` is given, ``category`` is inferred via
          :func:`get_category`.
        - If only ``category`` is given, ``outcome`` is set to the default for
          that category via :func:`get_default_outcome`.
        - If both are given they must agree, otherwise ``ValueError`` is raised.
        - ``code`` defaults to the outcome's integer value when ``< 0``.

        Args:
            category: Broad result category (or string name).
            outcome: Specific result outcome (or string name / integer value).
            reason: Optional free-text explanation.
            code: Numeric exit code; ``-1`` means "use outcome.value".

        Raises:
            ValueError: If ``category`` and ``outcome`` are inconsistent, or if
                ``outcome`` is not valid for the derived ``category``.
        """
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
        """Construct a ``Status`` from a raw mapping (e.g. deserialized JSON).

        Accepts keys ``category``, ``outcome`` (or legacy ``status``), ``reason``,
        and ``code``.  Extra keys raise ``TypeError``.
        """
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
        """Return a formatted label string, e.g. ``'PASS (SUCCESS)'``.

        Args:
            style: ``'none'`` for plain text, ``'rich'`` for Rich markup,
                ``'html'`` for ``<font color=...>`` HTML.
            glyph: Prepend the outcome glyph (✓/✗/⏱/…) when ``True``.
        """
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
        """Return the Rich markup color for this status (delegates to category)."""
        return self.category.rich_color()

    def hex_color(self) -> str:
        """Return the HTML hex color for this status (delegates to category)."""
        return self.category.hex_color()

    def glyph(self) -> str:
        """Return the Unicode glyph for this status (delegates to outcome)."""
        return self.outcome.glyph()

    @classmethod
    def SUCCESS(cls):
        """Create a ``Status`` with outcome ``SUCCESS`` and exit code 0."""
        self = cls()
        self.set(outcome=Outcome.SUCCESS, code=0)
        return self

    @classmethod
    def XFAIL(cls):
        """Create a ``Status`` with outcome ``XFAIL`` (expected failure)."""
        self = cls()
        self.set(outcome=Outcome.XFAIL)
        return self

    @classmethod
    def XDIFF(cls):
        """Create a ``Status`` with outcome ``XDIFF`` (expected diff)."""
        self = cls()
        self.set(outcome=Outcome.XDIFF)
        return self

    @classmethod
    def FAILED(cls, reason: str | None = None, code: int = -1):
        """Create a ``Status`` with outcome ``FAILED``."""
        self = cls()
        self.set(outcome=Outcome.FAILED, reason=reason, code=code)
        return self

    @classmethod
    def DIFFED(cls, reason: str | None = None, code: int = -1):
        """Create a ``Status`` with outcome ``DIFFED`` (output differed from baseline)."""
        self = cls()
        self.set(outcome=Outcome.DIFFED, reason=reason, code=code)
        return self

    @classmethod
    def TIMEOUT(cls, code: int = -1):
        """Create a ``Status`` with outcome ``TIMEOUT``."""
        self = cls()
        self.set(outcome=Outcome.TIMEOUT, code=code)
        return self

    @classmethod
    def ERROR(cls, reason: str | None = None, code: int = -1):
        """Create a ``Status`` with outcome ``ERROR`` (framework-level error)."""
        self = cls()
        self.set(outcome=Outcome.ERROR, reason=reason, code=code)
        return self

    @classmethod
    def BROKEN(cls, reason: str | None = None, code: int = -1):
        """Create a ``Status`` with outcome ``BROKEN`` (inconsistent job state)."""
        self = cls()
        self.set(outcome=Outcome.BROKEN, reason=reason, code=code)
        return self

    @classmethod
    def SKIPPED(cls, reason: str | None = None):
        """Create a ``Status`` with outcome ``SKIPPED``."""
        self = cls()
        self.set(outcome=Outcome.SKIPPED, reason=reason)
        return self

    @classmethod
    def BLOCKED(cls, reason: str | None = None):
        """Create a ``Status`` with outcome ``BLOCKED`` (dependency not satisfied)."""
        self = cls()
        self.set(outcome=Outcome.BLOCKED, reason=reason)
        return self

    @classmethod
    def CANCELLED(cls, reason: str | None = None):
        """Create a ``Status`` with outcome ``CANCELLED``."""
        self = cls()
        self.set(outcome=Outcome.CANCELLED, reason=reason)
        return self

    @classmethod
    def INTERRUPTED(cls, reason: str | None = None):
        """Create a ``Status`` with outcome ``INTERRUPTED`` and exit code ``SIGINT``."""
        import signal

        self = cls()
        reason = reason or "Keyboard interrupt"
        self.set(outcome=Outcome.INTERRUPTED, reason=reason, code=signal.SIGINT.value)
        return self


def get_category(arg: Outcome) -> "Category":
    """Return the :class:`Category` that contains the given :class:`Outcome`.

    Args:
        arg: The outcome to classify.

    Returns:
        The matching ``Category``.  Returns ``Category.NONE`` for ``Outcome.NONE``.
    """
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
    """Return the tuple of :class:`Outcome` values valid for the given :class:`Category`.

    Args:
        arg: The category to query.

    Returns:
        A tuple of all outcomes that belong to ``arg``.  For ``Category.NONE``
        returns ``(Outcome.NONE,)``.
    """
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
    """Return the canonical default :class:`Outcome` for a :class:`Category`.

    Used by :meth:`Status.set` when a category is supplied without an outcome.

    Args:
        arg: The category to query.

    Returns:
        ``SUCCESS`` for PASS, ``DIFFED`` for FAIL, ``CANCELLED`` for CANCEL,
        ``SKIPPED`` for SKIP, and ``NONE`` otherwise.
    """
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
