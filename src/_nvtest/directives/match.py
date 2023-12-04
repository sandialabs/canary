"""Generic mechanism for marking and selecting test files by keyword."""
import dataclasses
import fnmatch
import os
import sys
from typing import AbstractSet
from typing import Union

from .expression import Expression
from .expression import ParseError
from .p_expression import ParameterExpression


@dataclasses.dataclass
class KeywordMatcher:
    """A matcher for keywords which are present.

    Tries to match on any keywords, attached to the given items
    """

    __slots__ = ("own_kw_names",)

    own_kw_names: AbstractSet[str]

    def __call__(self, name: str) -> bool:
        return anymatch(self.own_kw_names, name, case_sensitive=False)


def deselect_by_keyword(
    keywords: AbstractSet[str], matchexpr: str
) -> Union[None, bool]:
    if not matchexpr:
        return None
    expr = _parse_expression(matchexpr, "Invalid expression passed to '-k'")
    return not expr.evaluate(KeywordMatcher(keywords))


@dataclasses.dataclass
class OptionMatcher:
    """A matcher for options which are present.

    Tries to match on any options, attached to the given items
    """

    __slots__ = ("own_opt_names",)

    own_opt_names: AbstractSet[str]

    def __call__(self, name: str) -> bool:
        return anymatch(self.own_opt_names, name)


def deselect_by_option(
    options: AbstractSet[str], option_expr: str
) -> Union[None, bool]:
    if not option_expr:
        return None
    expr = _parse_expression(option_expr, "Invalid option expression")
    return not expr.evaluate(OptionMatcher(options))


@dataclasses.dataclass
class NameMatcher:
    """A matcher for names.  The match expression can contain wildcards.

    Tries to match on any name, attached to the given items.
    """

    __slots__ = ("own_names",)

    own_names: AbstractSet[str]

    def __call__(self, name: str) -> bool:
        return anymatch(self.own_names, name)


def deselect_by_name(names: AbstractSet[str], names_expr: str) -> Union[None, bool]:
    if not names_expr:
        return None
    expr = _parse_expression(
        names_expr, "Invalid name expression", allow_wildcards=True
    )
    return not expr.evaluate(NameMatcher(names))


@dataclasses.dataclass
class PlatformMatcher:
    """A matcher for platform."""

    __slots__ = ("own_platform_names",)

    own_platform_names: AbstractSet[str]

    def __call__(self, name: str) -> bool:
        return anymatch(self.own_platform_names, name, case_sensitive=False)


def deselect_by_platform(platform_expr: str) -> Union[None, bool]:
    expr = _parse_expression(platform_expr, "Invalid platform expression")
    platforms = {sys.platform, sys.platform.lower()}
    if "SNLSYSTEM" in os.environ:
        platforms.add(os.environ["SNLSYSTEM"])
    if "NVTEST_PLATFORM" in os.environ:
        platforms.add(os.environ["NVTEST_PLATFORM"])
    return not expr.evaluate(PlatformMatcher(platforms))


def deselect_by_parameter(
    parameters: dict[str, object], parameter_expr: str
) -> Union[None, bool]:
    try:
        expr = ParameterExpression(parameter_expr)
    except ValueError:
        raise UsageError("Invalid expression passed to '-p'")
    return not expr.eval(parameters)


def _parse_expression(
    expr: str, exc_message: str, allow_wildcards: bool = False, _cache: dict = {}
) -> Expression:
    if expr in _cache:
        return _cache[expr]
    try:
        code = Expression.compile(expr, allow_wildcards=allow_wildcards)
        _cache[expr] = code
        return code
    except ParseError as e:
        if os.getenv("NVTEST_CONFIG_DEBUG"):
            raise
        raise UsageError(f"{exc_message}: {expr}: {e}") from None


def anymatch(
    items: AbstractSet[str], pattern: str, case_sensitive: bool = True
) -> bool:
    if not case_sensitive:
        items = {item.lower() for item in items}
        pattern = pattern.lower()
    return any(fnmatch.fnmatchcase(item, pattern) for item in items)


class UsageError(Exception):
    """Error in nvtest usage or invocation."""
