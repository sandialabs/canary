# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Generic ``Field`` that aggregates conditional values and reduces them to a result.

``Field`` pairs a ``Reducer`` with a list of ``Conditional`` items, evaluating
which items are active in a given context and folding them into a single value.
"""

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any
from typing import Generic
from typing import TypeVar

from .conditional import Conditional
from .reducer import Reducer

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class Field(Generic[T, R]):
    """A collection of conditional values reduced to a single result.

    - Store values as Conditional[T]
    - Evaluate which values are active in a context
    - Reduce active values with a Reducer[T, R]

    Attributes:
        reducer: The reduction strategy applied to the active values.
        items: Ordered list of conditional entries added via ``add``.
    """

    reducer: Reducer[T, R]
    items: list[Conditional[T]] = dc_field(default_factory=list)

    def add(self, value: T, *, when=None) -> None:
        """Append a new conditional entry.

        Args:
            value: The value to store.
            when: Optional activation condition (string or dict); ``None`` means always active.
        """
        self.items.append(Conditional.make(value, when=when))

    @classmethod
    def make(cls, reducer: Reducer[T, R]) -> "Field[T, R]":
        """Create an empty ``Field`` with the given ``reducer``.

        Args:
            reducer: The ``Reducer`` to apply during evaluation.

        Returns:
            A new, empty ``Field`` instance.
        """
        return cls(reducer=reducer)

    def eval(
        self,
        *,
        family: str | None = None,
        on_options: list[str] | None = None,
        keywords: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> R:
        """Evaluate active items and reduce them to a single result.

        Args:
            family: Test family name for conditional matching.
            on_options: Active option flags for conditional matching.
            keywords: Active keywords for conditional matching.
            parameters: Current parameter bindings for conditional matching.

        Returns:
            The reduced result of all active conditional values.
        """
        active: list[T] = []
        for c in self.items:
            if c.matches(
                family=family, on_options=on_options, keywords=keywords, parameters=parameters
            ):
                active.append(c.value)
        return self.reducer(active)
