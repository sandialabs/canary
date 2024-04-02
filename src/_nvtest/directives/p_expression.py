r"""Evaluate match expressions, as used by `-p`

The grammar is:

expression: expr? EOF
expr:       ident
ident:      ([a-zA-Z_]+\w(=|>=|>|<|<=|==|!=).*

The semantics are:

- Empty expression evaluates to False.
- ident evaluates to True of False according to a provided matcher function.
- or/and/not evaluate according to the usual boolean semantics.
"""

import io
import tokenize
from typing import Any
from typing import Callable


class ParameterExpression:
    def __init__(self, string: str) -> None:
        self.string = string
        self.expression = self.parse_expr(string)

    def __repr__(self) -> str:
        return self.string

    @staticmethod
    def parse_expr(expr: str) -> str:
        tokens = get_tokens(expr)
        parts = []
        while True:
            try:
                token = next(tokens)
            except StopIteration:
                break
            if token.type == tokenize.ENDMARKER:
                break
            elif token.type in (tokenize.ENCODING, tokenize.NEWLINE):
                continue
            elif token.type in (tokenize.STRING, tokenize.NUMBER):
                parts.append(token.string)
            elif token.type == tokenize.NAME:
                if parts and parts[-1] in ("==", "!=", ">", ">=", "<", "<="):
                    parts.append(f"{token.string!r}")
                else:
                    parts.append(token.string)
            elif token.type == tokenize.OP:
                string = token.string
                if string == "=":
                    string = "=="
                parts.append(string)
            elif token.type == tokenize.ERRORTOKEN and token.string == "!":
                token = next(tokens)
                assert token.type == tokenize.NAME
                parts.append(f"not_defined({token.string!r})")
            else:
                raise ValueError(f"Unknown token type {token} in parameter expression {expr}")
        return " ".join(parts)

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
