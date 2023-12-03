import io
import itertools
import tokenize
from io import StringIO
from typing import Any
from typing import Callable
from typing import Collection
from typing import Optional
from typing import Sequence
from typing import Type
from typing import Union

from .match import deselect_by_name
from .match import deselect_by_option
from .match import deselect_by_platform


class ParameterSet:
    def __init__(self, keys: list[str], values: Collection[Sequence[Any]]) -> None:
        self.keys: list[str] = keys
        self.values: Collection[Sequence[Any]] = values

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
        values: Collection[Sequence[Any]],
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        testname: Optional[str] = None,
    ) -> None:
        self.keys: list[str] = keys
        self.values: Collection[Sequence[Any]] = values
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
        argvalues: Collection[Union[Sequence[Any], Any]],
        options: Optional[str] = None,
        platforms: Optional[str] = None,
        testname: Optional[str] = None,
        file: Optional[str] = None,
    ):
        names: list[str] = []
        values: Collection[Sequence[Any]] = []
        if isinstance(argnames, str):
            names.extend([x.strip() for x in argnames.split(",") if x.strip()])
        else:
            names.extend(argnames)
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

    @staticmethod
    def centered_parameter_space(
        argnames: Union[str, Sequence[str]],
        argvalues: Collection[Union[Sequence[Any], Any]],
    ) -> tuple[list[str], list[list[float]]]:
        """Generate parameters for a centered parameter study

        Notes
        -----
        The centered parameter space computes parameter sets along multiple
        coordinate-based vectors, one per parameter, centered about the initial
        values.

        The centered_parameter_space takes steps along each orthogonal dimension.
        Each dimension is treated independently. The number of steps are taken in
        each direction, so that the total number of points in the parameter study is
        :math:`1+ 2\sum{n}`.

        >>> names, values = centered_parameter_space(
            "name_1,name_2", [(0, 5, 2), (0, 1, 2)]
        )
        >>> for row in values:
        ...     print(", ".join(f"{names[i]}={p}" for (i, p) in enumerate(row)))
        ...
        name_1=0, name_2=0
        name_1=-10, name_2=0
        name_1=-5, name_2=0
        name_1=5, name_2=0
        name_1=10, name_2=0
        name_1=0, name_2=-2
        name_1=0, name_2=-1
        name_1=0, name_2=1
        name_1=0, name_2=2

        """
        parameters: list[tuple[str, float, float, int]] = []
        names: list[str] = []
        if isinstance(argnames, str):
            names.extend([x.strip() for x in argnames.split(",") if x.strip()])
        else:
            names.extend(argnames)
        if len(names) <= 1:
            raise ValueError("Expected more than 1 parameter")
        if len(names) != len(argvalues):
            raise ValueError("Expected len(names) == len(values)")
        for (i, item) in enumerate(argvalues):
            try:
                initial_value, step_size, num_steps = item
            except ValueError:
                raise ValueError(f"Expected len(argvalues[{i}]) == 3") from None
            parameters.append((names[i], initial_value, step_size, num_steps))
        values: list[list[float]] = [[x[1] for x in parameters]]
        for i, parameter in enumerate(parameters):
            _, x, dx, steps = parameter
            for fac in range(-steps, steps + 1):
                if fac == 0:
                    continue
                space = [x[1] for x in parameters]
                space[i] = x + dx * fac
                values.append(space)
        return names, values


def append_if_unique(container, item):
    if item not in container:
        container.append(item)


def combine_parameter_sets(paramsets: list[ParameterSet]) -> list[dict[str, Any]]:
    """Perform a Cartesian product combination of parameter sets"""
    all_parameters: list[dict[str, Any]] = []
    if not paramsets:
        return all_parameters
    elif len(paramsets) == 1:
        paramset = paramsets[0]
        for values in paramset.values:
            parameters = {}
            for i, v in enumerate(values):
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
            for i, item in enumerate(group):
                for j, x in enumerate(item):
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

    def eval(self, parameters: dict[str, Any]) -> bool:
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
