# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import fnmatch
import io
import json
import os
import sys
import tokenize
from string import Template
from typing import AbstractSet
from typing import Any
from typing import Iterator
from typing import Type

from .expression import Expression
from .expression import ParameterExpression
from .third_party.color import colorize


class WhenResult:
    """Simple class holding the value of the result of a :class:`~When` evaluation

    Instances of this class contain two members: ``value`` and ``reason``.  ``value`` is ``True``
    if the underlying :class:`~When` expression evaluated to ``True`` else ``False``.  If
    ``value=False``, ``reason`` will contain the reason.

    """

    __slots__ = ("value", "reason")

    def __init__(self, value: bool, reason: str | None):
        self.value = value
        self.reason = reason


class When:
    """Implements the ``when=`` logic that controls the conditions under which a directive is run

    ``canary`` directives can be run depending on the options passed to ``canary`` on the command
    line.  E.g., a test may be parameterized on ``a`` only if run linux:
    ``canary.directives.parameterize('a', (1, 2, 3), when='platforms=linux')``.  This
    ``parameterize`` instance will only be active on ``linux`` platforms.

    Args:
      options: expression defining options under which the directive will be activated, e.g.,
        options='opt and baz'.  Options are typically passed on the command line.
      parameters: expression defining parameterizations under which the directive will be
        activated, e.g., ``parameters='cpus>1'``.
      testname: expression defining the testname under which the directive will be activated, e.g.
        testname='baz'.
      platforms: expression defining the platforms under which the directive will be activated, e.g.
        ``platform='linux'``.

    Notes:

    * The environment variable ``CANARY_PLATFORMS`` can be set to alternative platform names to
      activate directives requiring a specific platform

    Examples:

    >>> import canary
    >>> canary.directives.parameterize('gpus', (1, 4), when='platform=linux')

    """

    def __init__(
        self,
        *,
        options: str | None = None,
        keywords: str | None = None,
        parameters: str | None = None,
        testname: str | None = None,
        platforms: str | None = None,
    ):
        self.option_expr = options
        self.keyword_expr = keywords
        self.parameter_expr = parameters
        self.testname_expr = testname
        self.platform_expr = platforms

    @staticmethod
    def factory(input: str | dict[str, str] | None) -> "When":
        if isinstance(input, dict):
            return When(**input)
        elif input is None:
            return When()
        else:
            return When.from_string(input)

    @classmethod
    def from_string(cls: "Type[When]", input: str | None) -> "When":
        """Parse expression, such as

        ``when="options='not dbg' keywords='fast and regression'"``

        and return {"options": "not dbg", "keywords": "fast and regression"}

        """
        attrs = ("options", "keywords", "parameters", "testname", "platforms")
        name_map = {
            "option": "options",
            "parameter": "parameters",
            "platform": "platforms",
            "name": "testname",
        }
        if input in _when_cache:
            return _when_cache[input]
        elif input is None:
            self = cls()
            _when_cache[None] = self
            return self
        if not isinstance(input, str):
            raise TypeError("Expected input to be None, bool, or str")
        tokens = get_tokens(input)
        expressions: dict[str, str] = {}
        while True:
            try:
                token = next(tokens)
            except StopIteration:
                break
            except tokenize.TokenError:
                raise InvalidSyntax(token) from None
            if token.type == tokenize.ENDMARKER:
                break

            if token.type in (tokenize.ENCODING, tokenize.NEWLINE):
                continue

            if token.type != tokenize.NAME:
                raise InvalidSyntax(token)

            name = name_map.get(token.string, token.string)
            if name not in attrs:
                raise TypeError(f"when: got an unexpected keyword argument {name!r}")
            if name in expressions:
                raise InvalidSyntax(token, msg=f"keyword argument repeated: {name}")

            try:
                token = next(tokens)
            except StopIteration:
                raise InvalidSyntax(token)

            if (token.type, token.string) != (tokenize.OP, "="):
                raise InvalidSyntax(token)

            try:
                token = next(tokens)
            except StopIteration:
                raise InvalidSyntax(token)
            except tokenize.TokenError:
                raise InvalidSyntax(token)

            if token.type not in (tokenize.NAME, tokenize.STRING, tokenize.NEWLINE):
                raise InvalidSyntax(token)

            value = remove_surrounding_quotes(token.string)
            if name in ("testname", "options", "keywords", "platforms", "parameters"):
                expressions[name] = value

        self = cls(**expressions)
        _when_cache[input] = self
        return self

    def evaluate_platform_expression(self, **kwds: str) -> str | None:
        assert self.platform_expr is not None
        string = safe_substitute(self.platform_expr, **kwds)
        string = remove_surrounding_quotes(string)
        expr = Expression.compile(string, allow_wildcards=True)
        if not expr.evaluate(PlatformMatcher()):
            fmt = "@*{{platforms={0}}} evaluated to @*r{{False}} for platforms={1}"
            input = ",".join(PlatformMatcher().own_platform_names)
            reason = colorize(fmt.format(expr.string, input))
            return reason
        return None

    def evaluate_testname_expression(self, testname_arg: str | None, **kwds: str) -> str | None:
        assert self.testname_expr is not None
        if testname_arg is None:
            fmt = "@*{{testname={0}}} evaluated to @*r{{False}} for testname=None"
            reason = colorize(fmt.format(self.testname_expr))
            return reason
        string = safe_substitute(self.testname_expr, **kwds)
        string = remove_surrounding_quotes(string)
        expr = Expression.compile(string, allow_wildcards=True)
        if not expr.evaluate(NameMatcher({testname_arg})):
            fmt = "@*{{testname={0}}} evaluated to @*r{{False}} for testname={1}"
            reason = colorize(fmt.format(expr.string, testname_arg))
            return reason
        return None

    def evaluate_option_expression(self, options_arg: list[str] | None, **kwds: str) -> str | None:
        assert self.option_expr is not None
        options_arg = options_arg or []
        string = safe_substitute(self.option_expr, **kwds)
        string = remove_surrounding_quotes(string)
        expr = Expression.compile(string, allow_wildcards=True)
        if not expr.evaluate(OptionMatcher(set(options_arg))):
            fmt = "@*{{options={0}}} evaluated to @*r{{False}} for options={1}"
            reason = colorize(fmt.format(expr.string, json.dumps(options_arg)))
            return reason
        return None

    def evaluate_keyword_expression(
        self, keywords_arg: list[str] | None, **kwds: str
    ) -> str | None:
        assert self.keyword_expr is not None
        keywords_arg = keywords_arg or []
        string = safe_substitute(self.keyword_expr, **kwds)
        string = remove_surrounding_quotes(string)
        expr = Expression.compile(string, allow_wildcards=True)
        if not expr.evaluate(AnyMatcher(set(keywords_arg), False)):
            fmt = "@*{{keywords={0}}} evaluated to @*r{{False}} for keywords={1}"
            reason = colorize(fmt.format(expr.string, json.dumps(keywords_arg)))
            return reason
        return None

    def evaluate_parameter_expression(
        self, parameters_arg: dict[str, Any] | None, **kwds: str
    ) -> str | None:
        assert self.parameter_expr is not None
        parameters_arg = parameters_arg or {}
        string = safe_substitute(self.parameter_expr, **kwds)
        string = remove_surrounding_quotes(string)
        expr = ParameterExpression(string)
        if not expr.evaluate(parameters_arg):
            fmt = "@*{{parameters={0}}} evaluated to @*r{{False}} for parameters={1}"
            reason = colorize(fmt.format(expr.string, json.dumps(parameters_arg)))
            return reason
        return None

    def evaluate(
        self,
        *,
        testname: str | None = None,
        keywords: list[str] | None = None,
        on_options: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> WhenResult:
        kwds: dict[str, Any] = {}
        if testname is not None:
            kwds["testname"] = kwds["name"] = None
        if parameters is not None:
            kwds.update(parameters)
        for key in list(kwds.keys()):
            kwds[key.upper()] = kwds[key]

        if self.platform_expr is not None:
            reason = self.evaluate_platform_expression(**kwds)
            if reason is not None:
                return WhenResult(False, reason)

        if self.testname_expr is not None:
            reason = self.evaluate_testname_expression(testname, **kwds)
            if reason is not None:
                return WhenResult(False, reason)

        if self.option_expr is not None:
            reason = self.evaluate_option_expression(on_options, **kwds)
            if reason is not None:
                return WhenResult(False, reason)

        if self.keyword_expr is not None:
            reason = self.evaluate_keyword_expression(keywords, **kwds)
            if reason is not None:
                return WhenResult(False, reason)

        if self.parameter_expr is not None:
            reason = self.evaluate_parameter_expression(parameters, **kwds)
            if reason is not None:
                return WhenResult(False, reason)

        return WhenResult(True, None)


_when_cache: dict[str | None, When] = {}


@dataclasses.dataclass
class NameMatcher:
    """A matcher for names.  The match expression can contain wildcards.

    Tries to match on any name, attached to the given items.
    """

    __slots__ = ("own_names",)
    own_names: AbstractSet[str]

    def __call__(self, name: str) -> bool:
        return anymatch(self.own_names, name)


@dataclasses.dataclass
class OptionMatcher:
    """A matcher for options which are present.

    Tries to match on any options, attached to the given items
    """

    __slots__ = ("own_opt_names",)
    own_opt_names: AbstractSet[str]

    def __call__(self, name: str) -> bool:
        return anymatch(self.own_opt_names, name)


@dataclasses.dataclass
class AnyMatcher:
    """Tries to match on any options, attached to the given items"""

    __slots__ = ("own_names", "case_sensitive")
    own_names: AbstractSet[str]
    case_sensitive: bool

    def __call__(self, name: str) -> bool:
        return anymatch(self.own_names, name, case_sensitive=self.case_sensitive)


class PlatformMatcher:
    """A matcher for platform."""

    def __init__(self):
        self.own_platform_names = {sys.platform, sys.platform.lower()}
        if "SNLSYSTEM" in os.environ:
            self.own_platform_names.add(os.environ["SNLSYSTEM"])
        if "SNLCLUSTER" in os.environ:
            self.own_platform_names.add(os.environ["SNLCLUSTER"])
        if "SNLOS" in os.environ:
            self.own_platform_names.add(os.environ["SNLOS"])
        if "CANARY_PLATFORM" in os.environ:
            platforms = os.environ["CANARY_PLATFORM"].split(",")
            self.own_platform_names.update(platforms)

    def __call__(self, name: str) -> bool:
        if "any" in self.own_platform_names:
            return True
        return anymatch(self.own_platform_names, name, case_sensitive=False)


def match_any(code: str, items: list[str]) -> bool:
    expr = Expression.compile(code, allow_wildcards=True)
    return expr.evaluate(AnyMatcher(set(items), True))


def safe_substitute(arg: str, **kwds) -> str:
    if "$" in arg:
        t = Template(arg)
        return t.safe_substitute(**kwds)
    return arg.format(**kwds)


def get_tokens(code) -> Iterator[tokenize.TokenInfo]:
    fp = io.BytesIO(code.encode("utf-8"))
    return tokenize.tokenize(fp.readline)


def anymatch(items: AbstractSet[str], pattern: str, case_sensitive: bool = True) -> bool:
    if not case_sensitive:
        items = {item.lower() for item in items}
        pattern = pattern.lower()
    return any(fnmatch.fnmatchcase(item, pattern) for item in items)


def remove_surrounding_quotes(arg: str) -> str:
    if arg[:3] == '"""' and arg[-3:] == '"""':
        return remove_surrounding_quotes(arg[3:-3])
    elif arg[:3] == "'''" and arg[-3:] == "'''":
        return remove_surrounding_quotes(arg[3:-3])
    elif arg[:1] == "'" and arg[-1:] == "'":
        return remove_surrounding_quotes(arg[1:-1])
    elif arg[:1] == '"' and arg[-1:] == '"':
        return remove_surrounding_quotes(arg[1:-1])
    return arg


def when(
    input: str | bool | dict,
    keywords: list[str] | None = None,
    parameters: dict[str, Any] | None = None,
    testname: str | None = None,
    on_options: list[str] | None = None,
) -> bool:
    if isinstance(input, bool):
        return input
    expression: When
    assert isinstance(input, (str, dict))
    if isinstance(input, dict):
        expression = When(**input)
    else:
        expression = When.from_string(input)
    result = expression.evaluate(
        keywords=keywords,
        parameters=parameters,
        testname=testname,
        on_options=on_options,
    )
    return bool(result.value)


class InvalidSyntax(SyntaxError):
    def __init__(self, token, msg=None):
        line = f'when="{token.line}"'
        start = token.start[1]
        end = token.end[1]
        details = ("<expr>", 1, start + 7, line, 1, end + 7)
        super().__init__(msg or "invalid syntax", details)


class InvalidExpression(Exception):
    pass


class UsageError(Exception): ...
