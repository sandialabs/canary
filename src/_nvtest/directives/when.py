import dataclasses
import fnmatch
import io
import json
import os
import sys
import tokenize
from collections import namedtuple
from string import Template
from typing import AbstractSet
from typing import Any
from typing import Iterator
from typing import Optional
from typing import Union

from ..util.tty.color import colorize
from .expression import Expression
from .expression import ParseError
from .p_expression import ParameterExpression


class When:
    def __init__(self, input: Union[None, bool, str]) -> None:
        if input is not None and not isinstance(input, (bool, str)):
            raise ValueError("expected input to be None, bool, or str")
        self.input = input

    def __repr__(self):
        items = (f"{k}={v!r}" for k, v in self.__dict__.items())
        return "{}({})".format(type(self).__name__, ", ".join(items))

    def evaluate(
        self,
        testname: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ):
        result = namedtuple("result", "value, reason")
        if self.input is None:
            return result(True, None)
        elif self.input is True:
            return result(True, None)
        elif self.input is False:
            return result(False, "when=False")

        kwds: dict[str, Any] = {}
        if testname is not None:
            kwds["testname"] = kwds["name"] = None
        if parameters is not None:
            kwds.update(parameters)
        for key in list(kwds.keys()):
            kwds[key.upper()] = kwds[key]
        string = safe_substitute(self.input, **kwds)
        expression = CompositeExpression.parse(string)

        a = colorize('@*b{when="%s"}' % string)
        b = colorize("@*r{False}")
        value, expr_type = expression(
            testname=testname,
            on_options=on_options,
            keywords=keywords,
            parameters=parameters,
        )
        if value is True:
            return result(True, None)

        reason: str
        fmt = f"{a} evaluated to {b} for {expr_type}={{s}}"
        if expr_type == "testname":
            reason = fmt.format(s=testname)
        elif expr_type == "options":
            reason = fmt.format(s=json.dumps(on_options))
        elif expr_type == "keywords":
            reason = fmt.format(s=json.dumps(keywords))
        elif expr_type == "parameters":
            reason = fmt.format(s=json.dumps(parameters))
        elif expr_type == "platforms":
            reason = fmt.format(s=",".join(PlatformMatcher().own_platform_names))
        else:
            raise ValueError(f"Unknown expr_type {expr_type!r}, should never get here")

        return result(value, reason)


class CompositeExpression:
    attrs = ("options", "keywords", "parameters", "testname", "platforms")

    def __init__(self, *, __x=False) -> None:
        if not __x:
            raise ValueError(
                "CompositeExpression must be initialized through factory methods"
            )

    def __call__(
        self,
        *,
        testname: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        expr: Union[Expression, ParameterExpression, None]

        expr = getattr(self, "platforms", None)
        if expr is not None:
            if not expr.evaluate(PlatformMatcher()):
                return False, "platforms"

        expr = getattr(self, "testname", None)
        if expr is not None:
            if testname is None:
                return False, "testname"
            if not expr.evaluate(NameMatcher({testname})):
                return False, "testname"

        expr = getattr(self, "options", None)
        if expr is not None:
            if on_options is None:
                return False, "options"
            if not expr.evaluate(OptionMatcher(set(on_options))):
                return False, "options"

        expr = getattr(self, "keywords", None)
        if expr is not None:
            if keywords is None:
                return False, "keywords"
            if not expr.evaluate(AnyMatcher(set(keywords))):
                return False, "keywords"

        expr = getattr(self, "parameters", None)
        if expr is not None:
            if parameters is None:
                return False, "parameters"
            if not expr.evaluate(parameters):
                return False, "parameters"

        return True, ""

    @classmethod
    def parse(cls, input: str) -> "CompositeExpression":
        """[testname=expr] [parameters=expr] [options=expr] [keywords=expr]"""
        name_map = dict(
            option="options",
            parameter="parameters",
            platform="platforms",
            name="testname",
        )
        self = cls(_CompositeExpression__x=True)  # type: ignore
        setattr(self, "string", input)
        if not isinstance(input, str):
            raise TypeError("Expected input to be None, bool, or str")
        tokens = get_tokens(input)
        while True:
            try:
                token = next(tokens)
            except StopIteration:
                break
            if token.type == tokenize.ENDMARKER:
                break

            if token.type in (tokenize.ENCODING, tokenize.NEWLINE):
                continue

            if token.type != tokenize.NAME:
                raise InvalidSyntax(token)

            name = name_map.get(token.string, token.string)
            if name not in self.attrs:
                raise TypeError(f"when: got an unexpected keyword argument {name!r}")
            if hasattr(self, name):
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

            if token.type not in (tokenize.NAME, tokenize.STRING, tokenize.NEWLINE):
                raise InvalidSyntax(token)

            value = remove_surrounding_quotes(token.string)
            if name in ("testname", "options", "keywords", "platforms"):
                try:
                    setattr(self, name, Expression.compile(value, allow_wildcards=True))
                except ParseError:
                    raise InvalidSyntax(token, msg=f"invalid {name} expression")
            else:
                try:
                    setattr(self, name, ParameterExpression(value))
                except ValueError:
                    raise InvalidSyntax(token, msg=f"invalid {name} expression")

        return self


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

    __slots__ = ("own_names",)
    own_names: AbstractSet[str]

    def __call__(self, name: str) -> bool:
        return anymatch(self.own_names, name)


class PlatformMatcher:
    """A matcher for platform."""

    def __init__(self):
        self.own_platform_names = {sys.platform, sys.platform.lower()}
        if "SNLSYSTEM" in os.environ:
            self.own_platform_names.add(os.environ["SNLSYSTEM"])
        if "NVTEST_PLATFORM" in os.environ:
            self.own_platform_names.add(os.environ["NVTEST_PLATFORM"])

    def __call__(self, name: str) -> bool:
        return anymatch(self.own_platform_names, name, case_sensitive=False)


def safe_substitute(arg: str, **kwds) -> str:
    if "$" in arg:
        t = Template(arg)
        return t.safe_substitute(**kwds)
    return arg.format(**kwds)


def get_tokens(code) -> Iterator[tokenize.TokenInfo]:
    fp = io.BytesIO(code.encode("utf-8"))
    return tokenize.tokenize(fp.readline)


def anymatch(
    items: AbstractSet[str], pattern: str, case_sensitive: bool = True
) -> bool:
    if not case_sensitive:
        items = {item.lower() for item in items}
        pattern = pattern.lower()
    return any(fnmatch.fnmatchcase(item, pattern) for item in items)


def remove_surrounding_quotes(arg: str) -> str:
    s_quote, d_quote = "'''", '"""'
    tokens = get_tokens(arg)
    token = next(tokens)
    while token.type == tokenize.ENCODING:
        token = next(tokens)
    s = token.string
    if token.type == tokenize.STRING:
        if s.startswith((s_quote, d_quote)):
            return s[3:-3]
        return s[1:-1]
    return arg


def when(
    input: Union[str, bool],
    keywords: Optional[list[str]] = None,
    parameters: Optional[dict[str, Any]] = None,
    testname: Optional[str] = None,
    on_options: Optional[list[str]] = None,
) -> bool:
    if isinstance(input, bool):
        return input
    assert isinstance(input, str)
    expression = When(input)
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


class UsageError(Exception):
    ...
