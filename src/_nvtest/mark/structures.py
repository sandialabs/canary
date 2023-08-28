import io
import itertools
import tokenize
from io import StringIO
from types import NoneType
from types import SimpleNamespace as Namespace
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Optional
from typing import Sequence
from typing import Type
from typing import Union

from .match import deselect_by_name
from .match import deselect_by_option
from .match import deselect_by_platform


class ParameterSet:
    def __init__(self, keys: list[str], values: Iterable[Sequence[Any]]) -> None:
        self.keys: list[str] = keys
        self.values: Iterable[Sequence[Any]] = values

    def describe(self, indent=0) -> str:
        fp = StringIO()
        fp.write(f"{' ' * indent}{','.join(self.keys)} = ")
        p = []
        for row in self.values:
            p.append(",".join(str(_) for _ in row))
        fp.write("; ".join(p))
        return fp.getvalue()


class AbstractParameterSet:
    def __init__(
        self,
        keys: list[str],
        values: Iterable[Sequence[Any]],
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        testname: Optional[str] = None,
    ) -> None:
        self.keys: list[str] = keys
        self.values: Iterable[Sequence[Any]] = values
        self.option_expr: Union[str, None] = options
        self.platform_expr: Union[str, None] = platforms
        self.testname_expr: Union[str, None] = testname

    def describe(self, indent=0) -> str:
        fp = StringIO()
        fp.write(f"{' ' * indent}{','.join(self.keys)} = ")
        p = []
        for row in self.values:
            p.append(",".join(str(_) for _ in row))
        fp.write("; ".join(p))
        return fp.getvalue()

    def freeze(
        self,
        on_options: Optional[list[str]] = None,
        testname: Optional[str] = None,
    ) -> Union[ParameterSet, None]:
        if self.platform_expr is not None and deselect_by_platform(self.platform_expr):
            return None
        options = set(on_options or [])
        if self.option_expr and deselect_by_option(options, self.option_expr):
            return None
        if self.testname_expr and testname:
            if deselect_by_name({testname}, self.testname_expr):
                return None
        return ParameterSet(self.keys, self.values)

    @classmethod
    def parse(
        cls: Type["AbstractParameterSet"],
        argnames: Union[str, Sequence[str]],
        argvalues: Iterable[Union[Sequence[Any], Any]],
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        testname: Optional[str] = None,
        file: Optional[str] = None,
    ):
        names: list[str] = []
        values: Iterable[Sequence[Any]] = []
        if isinstance(argnames, str):
            names = [x.strip() for x in argnames.split(",") if x.strip()]
        if len(names) == 1:
            values = [(_,) for _ in argvalues]
        else:
            values = [_ for _ in argvalues]
        for row in values:
            if len(row) != len(names):
                msg = (
                    '{file}: in "parametrize" the number of names ({names_len}):\n'
                    "  {names}\n"
                    "must be equal to the number of values ({values_len}):\n"
                    "  {values}"
                )
                raise ValueError(
                    msg.format(
                        file=file or "",
                        values=row,
                        names=names,
                        names_len=len(names),
                        values_len=len(row),
                    )
                )
        return cls(
            names, values, options=options, platforms=platforms, testname=testname
        )


class String:
    def __init__(
        self,
        arg: Optional[str] = None,
        *,
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        testname: Optional[str] = None,
        parameters: Optional[str] = None,
    ) -> None:
        self.value = self.validate(arg)
        self.option_expr: Union[str, None] = options
        self.platform_expr: Union[str, None] = platforms
        self.testname_expr: Union[str, None] = testname
        self.parameter_expr: ParameterExpression = ParameterExpression(parameters)

    def validate(self, arg: Union[None, str]) -> Union[None, str]:
        if arg is not None:
            assert isinstance(arg, str)
        return arg

    def __str__(self) -> str:
        return self.value if self.value is not None else ""

    def freeze(
        self,
        on_options: Optional[list[str]] = None,
        testname: Optional[str] = None,
        parameters: Optional[dict[str, object]] = None,
    ) -> Union[None, str]:
        if self.value is None:
            return None
        if self.testname_expr and testname:
            if deselect_by_name({testname}, self.testname_expr):
                return None
        if self.platform_expr is not None and deselect_by_platform(self.platform_expr):
            return None
        if (
            parameters
            and self.parameter_expr
            and not self.parameter_expr.eval(parameters)
        ):
            return None
        options = set(on_options or [])
        if self.option_expr and deselect_by_option(options, self.option_expr):
            return None
        return str(self.value)

    def testname_matches(self, testname: Optional[str] = None) -> Union[bool, None]:
        if not self.testname_expr or not testname:
            return None
        return not deselect_by_name({testname}, self.testname_expr)


class Number:
    def __init__(
        self,
        arg: Optional[Union[int, float]] = None,
        *,
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        testname: Optional[str] = None,
        parameters: Optional[str] = None,
    ) -> None:
        self.value = self.validate(arg)
        self.option_expr: Union[str, None] = options
        self.platform_expr: Union[str, None] = platforms
        self.testname_expr: Union[str, None] = testname
        self.parameter_expr: ParameterExpression = ParameterExpression(parameters)

    def validate(self, arg: Union[None, int, float]) -> Union[None, int, float]:
        if arg is not None:
            assert isinstance(arg, (int, float))
        return arg

    def freeze(
        self,
        on_options: Optional[list[str]] = None,
        testname: Optional[str] = None,
        parameters: Optional[dict[str, object]] = None,
    ) -> Union[None, int, float]:
        if self.value is None:
            return None
        if self.platform_expr is not None and deselect_by_platform(self.platform_expr):
            return None
        if (
            parameters
            and self.parameter_expr
            and not self.parameter_expr.eval(parameters)
        ):
            return None
        options = set(on_options or [])
        if self.option_expr and deselect_by_option(options, self.option_expr):
            return None
        if self.testname_expr and testname:
            if deselect_by_name({testname}, self.testname_expr):
                return None
        if isinstance(self.value, int):
            return int(self.value)
        return float(self.value)


class Boolean:
    def __init__(
        self,
        arg: Optional[bool] = None,
        *,
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        testname: Optional[str] = None,
        parameters: Optional[str] = None,
    ) -> None:
        self.value = self.validate(arg)
        self.option_expr: Union[str, None] = options
        self.platform_expr: Union[str, None] = platforms
        self.testname_expr: Union[str, None] = testname
        self.parameter_expr: ParameterExpression = ParameterExpression(parameters)
        self.reason: str = ""

    def validate(self, arg: Union[None, bool]) -> Union[None, bool]:
        if arg is not None:
            assert isinstance(arg, bool), arg
        return arg

    def freeze(
        self,
        on_options: Optional[list[str]] = None,
        testname: Optional[str] = None,
        parameters: Optional[dict[str, object]] = None,
    ) -> Union[None, bool]:
        if self.value is None:
            return None
        if self.platform_expr is not None and deselect_by_platform(self.platform_expr):
            self.reason = "platform expression"
            return not self.value
        if (
            parameters
            and self.parameter_expr
            and not self.parameter_expr.eval(parameters)
        ):
            self.reason = "parameter expression"
            return not self.value
        options = set(on_options or [])
        if self.option_expr and deselect_by_option(options, self.option_expr):
            self.reason = "option expression"
            return not self.value
        if self.testname_expr and testname:
            if deselect_by_name({testname}, self.testname_expr):
                self.reason = "test name expression"
                return not self.value
        return bool(self.value)


class FileAsset:
    def __init__(
        self,
        src: str,
        *,
        action: str,
        dst: Optional[str] = None,
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        parameters: Optional[str] = None,
        testname: Optional[str] = None,
    ) -> None:
        assert action in ("copy", "link", "sources")
        assert isinstance(src, str)
        self.src = src
        assert isinstance(dst, (str, NoneType))
        self.dst = dst
        self.action = action
        self.option_expr: Union[str, None] = options
        self.platform_expr: Union[str, None] = platforms
        self.parameter_expr: ParameterExpression = ParameterExpression(parameters)
        self.testname_expr: Union[str, None] = testname

    def freeze(
        self,
        on_options: Optional[list[str]] = None,
        testname: Optional[str] = None,
        parameters: Optional[dict[str, object]] = None,
    ) -> Union[None, Namespace]:
        if self.src is None:
            return None
        if self.platform_expr is not None and deselect_by_platform(self.platform_expr):
            return None
        if (
            parameters
            and self.parameter_expr
            and not self.parameter_expr.eval(parameters)
        ):
            return None
        options = set(on_options or [])
        if self.option_expr and deselect_by_option(options, self.option_expr):
            return None
        if self.testname_expr and testname:
            if deselect_by_name({testname}, self.testname_expr):
                return None
        return Namespace(action=self.action, src=self.src, dst=self.dst)


def append_if_unique(container, item):
    if item not in container:
        container.append(item)


def combine_parameter_sets(paramsets: list[ParameterSet]) -> list[dict[str, object]]:
    """Perform a Cartesian product combination of parameter sets"""
    all_parameters: list[dict[str, object]] = []
    if not paramsets:
        return all_parameters
    elif len(paramsets) == 1:
        paramset = paramsets[0]
        for values in paramset.values:
            parameters = {}
            for (i, v) in enumerate(values):
                parameters[paramset.keys[i]] = v
            append_if_unique(all_parameters, parameters)
    else:
        keys, values = [], []
        for paramset in paramsets:
            keys.append(paramset.keys)
            values.append(paramset.values)
        groups = itertools.product(*values)
        for group in groups:
            parameters = {}
            for (i, item) in enumerate(group):
                for (j, x) in enumerate(item):
                    parameters[keys[i][j]] = x
            append_if_unique(all_parameters, parameters)
    return all_parameters


def get_tokens(code):
    fp = io.BytesIO(code.encode("utf-8"))
    tokens = tokenize.tokenize(fp.readline)
    return tokens


class ParameterExpression:
    def __init__(self, expression: Optional[str] = None) -> None:
        if expression is not None:
            expression = self.parse_expr(expression)
        self.expression = expression

    def __bool__(self) -> bool:
        return self.expression is not None

    @staticmethod
    def parse_expr(expr: str) -> str:
        tokens = get_tokens(expr)
        token = next(tokens)
        while token == tokenize.ENCODING:
            token = next(token)
        negate_next = False
        parts = []
        for token in tokens:
            if negate_next:
                negate_next = False
                assert token.type == tokenize.NAME
                parts.append(f"not_defined({token.string!r})")
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
                negate_next = True
            elif token.type == tokenize.NEWLINE:
                break
            else:
                raise ValueError(
                    f"Unknown token type {token} in parameter expression {expr}"
                )
        return " ".join(parts)

    def eval(self, parameters: dict[str, object]) -> bool:
        global_vars = dict(parameters)
        global_vars["not_defined"] = not_defined(list(parameters.keys()))
        local_vars: dict = {}
        assert isinstance(self.expression, str)
        return bool(eval(self.expression, global_vars, local_vars))


def not_defined(names: list[str]) -> Callable:
    def inner(name):
        return name not in names

    return inner
