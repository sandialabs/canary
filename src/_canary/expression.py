# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import ast
import dataclasses
import enum
import io
import re
import tokenize
import types
from typing import Any
from typing import Callable
from typing import Iterator
from typing import Mapping
from typing import NoReturn
from typing import Sequence

__all__ = [
    "Expression",
    "ParseError",
]


class TokenType(enum.Enum):
    LPAREN = "left parenthesis"
    RPAREN = "right parenthesis"
    OR = "or"
    AND = "and"
    NOT = "not"
    WILDCARD = "wildcard"
    IDENT = "identifier"
    EOF = "end of input"


@dataclasses.dataclass(frozen=True)
class Token:
    __slots__ = ("type", "value", "pos")
    type: TokenType
    value: str
    pos: int


class ParseError(Exception):
    """The expression contains invalid syntax.

    :param column: The column in the line where the error occurred (1-based).
    :param message: A description of the error.
    """

    def __init__(self, column: int, message: str) -> None:
        self.column = column
        self.message = message

    def __str__(self) -> str:
        return f"at column {self.column}: {self.message}"


class Scanner:
    __slots__ = ("tokens", "current")
    ident_regex = r"(:?\w|:|\+|-|\.|\[|\]|\\|/)+"

    def __init__(self, input: str) -> None:
        self.tokens = self.lex(input)
        self.current = next(self.tokens)

    def lex(self, input: str) -> Iterator[Token]:
        pos = 0
        while pos < len(input):
            if input[pos] in (" ", "\t"):
                pos += 1
            elif input[pos] == "(":
                yield Token(TokenType.LPAREN, "(", pos)
                pos += 1
            elif input[pos] == ")":
                yield Token(TokenType.RPAREN, ")", pos)
                pos += 1
            else:
                match = re.match(self.ident_regex, input[pos:])
                if match:
                    value = match.group(0)
                    if value == "or":
                        yield Token(TokenType.OR, value, pos)
                    elif value == "and":
                        yield Token(TokenType.AND, value, pos)
                    elif value == "not":
                        yield Token(TokenType.NOT, value, pos)
                    else:
                        yield Token(TokenType.IDENT, value, pos)
                    pos += len(value)
                else:
                    raise ParseError(
                        pos + 1,
                        f'unexpected character "{input[pos]}"',
                    )
        yield Token(TokenType.EOF, "", pos)

    def accept(self, type: TokenType, *, reject: bool = False) -> Token | None:
        if self.current.type is type:
            token = self.current
            if token.type is not TokenType.EOF:
                self.current = next(self.tokens)
            return token
        if reject:
            self.reject((type,))
        return None

    def reject(self, expected: Sequence[TokenType]) -> NoReturn:
        raise ParseError(
            self.current.pos + 1,
            "expected {}; got {}".format(
                " OR ".join(type.value for type in expected),
                self.current.type.value,
            ),
        )


class WildcardScanner(Scanner):
    ident_regex = r"(:?\w|:|\*|\?|\+|-|\.|\[|\]|\\|/)+"


# True, False and None are legal match expression identifiers,
# but illegal as Python identifiers. To fix this, this prefix
# is added to identifiers in the conversion to Python AST.
IDENT_PREFIX = "$"


def expression(s: Scanner) -> ast.Expression:
    if s.accept(TokenType.EOF):
        ret: ast.expr = ast.Constant(False)
    else:
        ret = expr(s)
        s.accept(TokenType.EOF, reject=True)
    return ast.fix_missing_locations(ast.Expression(ret))


def expr(s: Scanner) -> ast.expr:
    ret = and_expr(s)
    while s.accept(TokenType.OR):
        rhs = and_expr(s)
        ret = ast.BoolOp(ast.Or(), [ret, rhs])
    return ret


def and_expr(s: Scanner) -> ast.expr:
    ret = not_expr(s)
    while s.accept(TokenType.AND):
        rhs = not_expr(s)
        ret = ast.BoolOp(ast.And(), [ret, rhs])
    return ret


def not_expr(s: Scanner) -> ast.expr:
    if s.accept(TokenType.NOT):
        return ast.UnaryOp(ast.Not(), not_expr(s))
    if s.accept(TokenType.LPAREN):
        ret = expr(s)
        s.accept(TokenType.RPAREN, reject=True)
        return ret
    ident = s.accept(TokenType.IDENT)
    if ident:
        return ast.Name(IDENT_PREFIX + ident.value, ast.Load())
    s.reject((TokenType.NOT, TokenType.LPAREN, TokenType.IDENT))


class MatcherAdapter(Mapping[str, bool]):
    """Adapts a matcher function to a locals mapping as required by eval()."""

    def __init__(self, matcher: Callable[[str], bool]) -> None:
        self.matcher = matcher

    def __getitem__(self, key: str) -> bool:
        return self.matcher(key[len(IDENT_PREFIX) :])

    def __iter__(self) -> Iterator[str]:
        raise NotImplementedError()

    def __len__(self) -> int:
        raise NotImplementedError()


class Expression:
    r"""Evaluate match expressions, as used by `-k` and `-m`.

    The grammar is:

    .. code-block:: console

      expression: expr? EOF
      expr:       and_expr ('or' and_expr)*
      and_expr:   not_expr ('and' not_expr)*
      not_expr:   'not' not_expr | '(' expr ')' | ident
      ident:      (\w|:|\+|-|\.|\[|\]|\\|/)+

    The semantics are:

    - Empty expression evaluates to False.
    - ident evaluates to True of False according to a provided matcher function.
    - or/and/not evaluate according to the usual boolean semantics.

    The expression can be evaluated against different matchers.
    """

    __slots__ = ("code", "string")

    def __init__(self, code: types.CodeType, string: str) -> None:
        self.code = code
        self.string = string

    def __repr__(self):
        return self.string

    @classmethod
    def compile(self, input: str, allow_wildcards: bool = False) -> "Expression":
        """Compile a match expression.

        :param input: The input expression - one line.
        """
        scanner: Scanner = WildcardScanner(input) if allow_wildcards else Scanner(input)
        astexpr = expression(scanner)
        code: types.CodeType = compile(
            astexpr,
            filename="<canary match expression>",
            mode="eval",
        )
        return Expression(code, input)

    def evaluate(self, matcher: Callable[[str], bool]) -> bool:
        """Evaluate the match expression.

        :param matcher:
            Given an identifier, should return whether it matches or not.
            Should be prepared to handle arbitrary strings as input.

        :returns: Whether the expression matches or not.
        """
        ret: bool = eval(self.code, {"__builtins__": {}}, MatcherAdapter(matcher))
        return ret


class ParameterExpression:
    r"""Evaluate match expressions, as used by `-p`

    The grammar is:

    expression: expr? EOF
    expr:       ident
    ident:      ``([a-zA-Z_]+\w(=|>=|>|<|<=|==|!=).*``

    The semantics are:

    - Empty expression evaluates to False.
    - ident evaluates to True of False according to a provided matcher function.
    - or/and/not evaluate according to the usual boolean semantics.
    """

    def __init__(self, string: str) -> None:
        self.string = string
        self.expression = self.parse_expr(string)

    def __repr__(self) -> str:
        return self.string

    @staticmethod
    def parse_expr(expr: str) -> str:
        TokenInfo = tokenize.TokenInfo
        parts: list[tokenize.TokenInfo] = []
        tokens = get_tokens(expr)
        STRLIKE = (tokenize.STRING, tokenize.NAME)
        KEYWORDS = ("and", "or", "else", "if")
        while True:
            try:
                token = next(tokens)
            except StopIteration:
                break
            if token.type == tokenize.ENDMARKER:
                break
            elif token.type in (tokenize.ENCODING, tokenize.NEWLINE):
                continue
            elif token.type in STRLIKE and token.string in KEYWORDS:
                token = TokenInfo(tokenize.STRING, token.string, token.start, token.end, token.line)
                parts.append(token)
            elif token.type in STRLIKE and parts and parts[-1].type == tokenize.NUMBER:
                # This situation can arise for something like `dimension = 2D`
                start = parts[-1].start
                string = repr(f"{parts[-1].string}{token.string}")
                parts[-1] = TokenInfo(tokenize.STRING, string, start, token.end, token.line)
            elif token.type in (tokenize.STRING, tokenize.NUMBER):
                parts.append(token)
            elif token.type == tokenize.NAME:
                if parts and parts[-1].type == tokenize.OP:
                    # This situation can arise for something like `var = val`
                    string = repr(token.string)
                    token = TokenInfo(tokenize.STRING, string, token.start, token.end, token.line)
                    parts.append(token)
                else:
                    parts.append(token)
            elif token.type == tokenize.OP:
                if token.string == "=":
                    token = TokenInfo(tokenize.OP, "==", token.start, token.end, token.line)
                elif token.string == "!":
                    # This situation can arise for something like `!cpus`
                    start = token.start
                    token = next(tokens)
                    assert token.type == tokenize.NAME
                    string = f"not_defined({token.string!r})"
                    token = TokenInfo(tokenize.ENDMARKER, string, start, token.end, token.line)
                parts.append(token)
            elif token.type == tokenize.ERRORTOKEN and token.string == "!":
                start = token.start
                token = next(tokens)
                assert token.type == tokenize.NAME
                string = f"not_defined({token.string!r})"
                token = TokenInfo(tokenize.ENDMARKER, string, start, token.end, token.line)
                parts.append(token)
            else:
                raise ValueError(f"Unknown token type {token} in parameter expression {expr}")
        return " ".join(_.string for _ in parts)

    def evaluate(self, parameters: dict[str, Any]) -> bool:
        global_vars = dict(parameters)
        global_vars["not_defined"] = not_defined(list(parameters.keys()))
        local_vars: dict = {}
        assert isinstance(self.expression, str)
        try:
            return bool(eval(self.expression, global_vars, local_vars))
        except NameError:
            return False


def not_defined(names: list[str]) -> Callable:
    def inner(name):
        return name not in names

    return inner


def get_tokens(code):
    fp = io.BytesIO(code.encode("utf-8"))
    tokens = tokenize.tokenize(fp.readline)
    return tokens
