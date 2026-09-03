# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Conditional value wrapper that pairs a value with a ``When`` predicate.

The ``Conditional`` dataclass is used throughout the directive system to
associate a typed value with an activation condition that can be evaluated
against test context (family, options, parameters, keywords).
"""

from dataclasses import dataclass
from typing import Any
from typing import Generic
from typing import TypeVar

from .. import when as m_when

WhenType = str | dict[str, str]
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Conditional(Generic[T]):
    """A value paired with a ``When`` predicate.

    Attributes:
        value: The wrapped value, activated only when ``when`` evaluates to true.
        when: The ``When`` predicate controlling activation.
    """

    value: T
    when: m_when.When

    @classmethod
    def make(cls, value: T, *, when: WhenType | None = None) -> "Conditional[T]":
        """Construct a ``Conditional`` from a raw ``when`` specification.

        Args:
            value: The value to wrap.
            when: A string or dict encoding the activation condition, or ``None``
                to create an unconditionally active entry.

        Returns:
            A new ``Conditional`` instance.
        """
        return cls(value=value, when=m_when.When.factory(when))

    def matches(
        self,
        *,
        family: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        keywords: list[str] | None = None,
    ) -> bool:
        """Evaluate whether this conditional is active in the given test context.

        Args:
            family: Test family name to match against.
            on_options: Active ``on_options`` flags.
            parameters: Current parameter bindings.
            keywords: Active test keywords.

        Returns:
            ``True`` if the ``when`` predicate passes, ``False`` otherwise.
        """
        r = self.when.evaluate(
            testname=family, on_options=on_options, parameters=parameters, keywords=keywords
        )
        return r.value
