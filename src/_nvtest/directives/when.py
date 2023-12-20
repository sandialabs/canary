import dataclasses
import fnmatch
import io
import json
import os
import sys
import tokenize
from string import Template
from types import SimpleNamespace
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
    def __init__(self, input: Optional[Union[str, bool]] = None) -> None:
        self.input = input

    def evaluate(
        self,
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> SimpleNamespace:
        if self.input in (None, True):
            # By default, when=True
            return SimpleNamespace(value=True, reason=None)
        elif self.input is False:
            return SimpleNamespace(value=False, reason="when=False")
        assert isinstance(self.input, str)

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
            testname=testname, on_options=on_options, parameters=parameters
        )
        result = SimpleNamespace(value=value, reason=expr_type)
        if not result.value:
            reason = f"{a} evaluated to {b} for {expr_type}={{s}}"
            if expr_type == "testname":
                result.reason = reason.format(s=testname)
            elif expr_type == "options":
                result.reason = reason.format(s=json.dumps(on_options))
            elif expr_type == "parameters":
                result.reason = reason.format(s=json.dumps(parameters))
        return result


class CompositeExpression:
    def __init__(
        self, expressions: dict[str, Union[Expression, ParameterExpression]], input: str
    ) -> None:
        self.expressions = expressions
        self.sting = input

    def __call__(
        self,
        *,
        testname: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        for (expr_type, expr) in self.expressions.items():
            if expr_type == "platforms":
                if not expr.evaluate(PlatformMatcher()):  # type: ignore
                    return False, expr_type
            elif expr_type == "testname":
                if testname is None:
                    return False, expr_type
                elif not expr.evaluate(NameMatcher({testname})):  # type: ignore
                    return False, expr_type
            elif expr_type == "options":
                opts = set(on_options or [])
                if on_options is None:
                    return False, expr_type
                elif not expr.evaluate(OptionMatcher(opts)):  # type: ignore
                    return False, expr_type
            elif expr_type == "parameters":
                if parameters is None:
                    return False, expr_type
                elif not expr.evaluate(parameters):  # type: ignore
                    return False, expr_type
        return True, ""

    @classmethod
    def parse(cls, input: str) -> "CompositeExpression":
        """[testname=expr] [parameters=expr] [options=expr]"""
        expressions: dict[str, Union[Expression, ParameterExpression]] = {}
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

            tok_details = cls.tok_details(token)
            if token.type != tokenize.NAME:
                raise SyntaxError("invalid syntax", tok_details)

            name = token.string
            if name in ("option", "parameter", "platform"):
                name += "s"
            elif name == "name":
                name = "testname"
            if name in expressions:
                raise SyntaxError(f"keyword argument repeated: {name}", tok_details)
            if name not in ("options", "parameters", "testname", "platforms"):
                raise TypeError(f"when: got an unexpected keyword argument {name!r}")

            try:
                token = next(tokens)
            except StopIteration:
                raise SyntaxError(token, tok_details)

            if (token.type, token.string) != (tokenize.OP, "="):
                raise SyntaxError("invalid syntax", tok_details)

            try:
                token = next(tokens)
            except StopIteration:
                raise SyntaxError("invalid syntax", tok_details)

            if token.type not in (tokenize.NAME, tokenize.STRING):
                raise SyntaxError("invalid syntax", tok_details)

            expression: Union[Expression, ParameterExpression]
            value = remove_surrounding_quotes(token.string)
            if name in ("testname", "options", "platforms"):
                try:
                    expression = Expression.compile(value, allow_wildcards=True)
                except ParseError:
                    raise SyntaxError(f"invalid {name} expression", tok_details)
            else:
                assert name == "parameters", name
                try:
                    expression = ParameterExpression(value)
                except ValueError:
                    raise SyntaxError(f"invalid {name} expression", tok_details)
            expressions[name] = expression
        return cls(expressions, input)

    @staticmethod
    def tok_details(token: tokenize.TokenInfo) -> tuple:
        line = f'when="{token.line}"'
        start = token.start[1]
        end = token.end[1]
        return ("<expr>", 1, start + 7, line, 1, end + 7)


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


class UsageError(Exception):
    ...
