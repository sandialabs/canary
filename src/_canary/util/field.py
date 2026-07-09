# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

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
    """

    reducer: Reducer[T, R]
    items: list[Conditional[T]] = dc_field(default_factory=list)

    def add(self, value: T, *, when=None) -> None:
        self.items.append(Conditional.make(value, when=when))

    @classmethod
    def make(cls, reducer: Reducer[T, R]) -> "Field[T, R]":
        return cls(reducer=reducer)

    def eval(
        self,
        *,
        family: str | None = None,
        on_options: list[str] | None = None,
        keywords: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> R:
        active: list[T] = []
        for c in self.items:
            if c.matches(
                family=family, on_options=on_options, keywords=keywords, parameters=parameters
            ):
                active.append(c.value)
        return self.reducer(active)
