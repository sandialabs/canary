"""
Test statuses
=============

Tests can receive one of the following statuses:

.. hlist::
   :columns: 3

   * :ref:`stat-masked`
   * :ref:`stat-created`
   * :ref:`stat-pending`
   * :ref:`stat-ready`
   * :ref:`stat-running`
   * :ref:`stat-cancelled`
   * :ref:`stat-skipped`
   * :ref:`stat-diffed`
   * :ref:`stat-failed`
   * :ref:`stat-timeout`
   * :ref:`stat-success`
   * :ref:`stat-xfail`
   * :ref:`stat-xdiff`

.. _stat-masked:

masked
------

The test was found in the search path but was filtered out of the list of tests to run.

.. _stat-created:

created
-------

The test case object has been instantiated.

.. _stat-ready:

ready
-----

The test case is setup and ready to run.

.. _stat-pending:

pending
-------

The test case is waiting for one or more dependencies.

.. _stat-running:

running
-------

The test case is currently running.

.. _stat-cancelled:

cancelled
---------

The test case was cancelled (usually by a keyboard interrupt).

.. _stat-skipped:

skipped
-------

The test case was skipped due to a failed dependency or skipped at runtime by exiting a ``63`` exit code.

.. admonition:: Tip

   Don't explicitly exit with code ``63``.  Instead, exit with ``nvtest.skip_exit_status`` or raise a ``nvtest.TestSkipped`` exception.

.. _stat-diffed:

diffed
------

A test diffs if it exits with a ``64`` exit code.

.. admonition:: Tip

   Don't explicitly exit with code ``64``.  Instead, exit with ``nvtest.diff_exit_status`` or raise a ``nvtest.TestDiffed`` exception.

.. _stat-failed:

failed
------

A test fails if it exits with any nonzero code not previously defined.

.. admonition:: Tip

   To explicitly mark a test as failed, exit with ``nvtest.fail_exit_status`` or raise a ``nvtest.TestFailed`` exception.

.. _stat-timeout:

timeout
-------

The test exceeded its allowed run time.

.. _stat-success:

success
-------

A test is considered successfully passed if it exits with a ``0`` exit code.

.. _stat-xfail:

xfail
-----

The test is marked as :ref:`expected to fail<directive-xfail>`

.. _stat-xdiff:

xdiff
-----

The test is marked as :ref:`expected to diff<directive-xdiff>`
"""

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
