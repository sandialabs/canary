# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from typing import Any
from typing import Generic
from typing import TypeVar

from .. import when as m_when

WhenType = str | dict[str, str]
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Conditional(Generic[T]):
    value: T
    when: m_when.When

    @classmethod
    def make(cls, value: T, *, when: WhenType | None = None) -> "Conditional[T]":
        return cls(value=value, when=m_when.When.factory(when))

    def matches(
        self,
        *,
        family: str | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        keywords: list[str] | None = None,
    ) -> bool:
        r = self.when.evaluate(
            testname=family,
            on_options=on_options,
            parameters=parameters,
            keywords=keywords,
        )
        return r.value
