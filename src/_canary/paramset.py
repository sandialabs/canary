# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import itertools
import random
from io import StringIO
from typing import Any
from typing import Sequence
from typing import Type


class ParameterSet:
    """Data type that stores a test file's parameters from which test cases are instantiated.  Data
    is stored in a two-dimensional table given by ``values`` with associated column labels given by
    ``keys``.  The number of columns in ``values`` must equal the number of ``keys``.

    Args:
      keys: names of parameters
      values: table of values

    Notes:

    The ``ParameterSet`` is most easily created through one of its class factory methods.

    """

    def __init__(self, keys: list[str], values: Sequence[Sequence[Any]]) -> None:
        self.keys: list[str] = keys
        self.values: list[list[Any]] = []
        for i, item in enumerate(values):
            if len(item) != len(self.keys):
                n = len(self.keys)
                raise ValueError(f"expected {n} items in row {i + 1}")
            else:
                self.values.append(list(item))

    def __iter__(self):
        for row in self.values:
            yield [(self.keys[i], value) for i, value in enumerate(row)]

    def describe(self, indent=0) -> str:
        fp = StringIO()
        fp.write(f"{' ' * indent}{','.join(self.keys)} = ")
        p = []
        for row in self.values:
            p.append(",".join(str(_) for _ in row))
        fp.write("; ".join(p))
        return fp.getvalue()

    @classmethod
    def list_parameter_space(
        cls: Type["ParameterSet"],
        argnames: str | Sequence[str],
        argvalues: list[Sequence[Any] | Any],
        file: str | None = None,
    ) -> "ParameterSet":
        """
        Create a ParameterSet

        Args:
          argnames: comma-separated string denoting one or more parameter names,
            r a list/tuple of names
          argvalues: If only one ``argname`` was specified, ``argvalues`` is a list of values.
            If ``N`` ``argnames`` were specified, ``argvalues`` is a 2D list of values
            where each column are the values for its respective ``argname``.

        Examples:

        >>> p = ParameterSet.list_parameter_space(
        ... "a,b", [[1, 2], [3, 4]])
        >>> p.keys
        ['a', 'b']
        >>> p.values
        [[1, 2], [3, 4]]

        """
        names: list[str] = []
        values: list[Sequence[Any]] = []
        if isinstance(argnames, str):
            names.extend([x.strip() for x in argnames.split(",") if x.strip()])
        else:
            names.extend(argnames)
        for argvalue in argvalues:
            if is_scalar(argvalue):
                values.append((argvalue,))
            else:
                values.append(argvalue)
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
        self = cls(names, values)
        return self

    @classmethod
    def centered_parameter_space(
        cls: Type["ParameterSet"],
        argnames: str | Sequence[str],
        argvalues: list[Sequence[Any] | Any],
        file: str | None = None,
    ) -> "ParameterSet":
        r"""Generate parameters for a centered parameter study

        Args:
          argnames: Same arguments as for ``ParameterSpace.list_parameter_space``
          argvalues: 2D list of values
            * argvalues[i, 0] is the initial value for the ith argname
            * argvalues[i, 1] is the steps size for the ith argname
            * argvalues[i, 2] is the number of steps for the ith argname

        Notes:

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
        names: list[str] = []
        if isinstance(argnames, str):
            names.extend([x.strip() for x in argnames.split(",") if x.strip()])
        else:
            names.extend(argnames)
        if len(names) <= 1:
            raise ValueError(
                f"{file}: parameterize({argnames}, ...): expected more than 1 parameter name"
            )
        if len(names) != len(argvalues):
            raise ValueError(
                f"{file}: parameterize({argnames}, ...): expected len(names) == len(values)"
            )
        parameters: list[tuple[str, float, float, int]] = []
        for i, item in enumerate(argvalues):
            try:
                initial_value, step_size, num_steps = item
            except ValueError:
                raise ValueError(
                    f"{file}: parameterize({argnames}, ...): expected len(argvalues[{i}]) == 3"
                ) from None
            parameters.append((names[i], initial_value, step_size, int(num_steps)))
        values: list[list[float]] = [[x[1] for x in parameters]]
        for i, parameter in enumerate(parameters):
            _, x, dx, steps = parameter
            for fac in range(-steps, steps + 1):
                if fac == 0:
                    continue
                space = [x[1] for x in parameters]
                space[i] = x + dx * fac
                values.append(space)
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
        self = cls(names, values)
        return self

    @classmethod
    def random_parameter_space(
        cls: Type["ParameterSet"],
        argnames: str | Sequence[str],
        argvalues: list[Sequence[Any] | Any],
        samples: int = 10,
        random_seed: float = 1234.0,
        file: str | None = None,
    ) -> "ParameterSet":
        """Generate random parameter space"""
        random.seed(random_seed)
        names: list[str] = []
        if isinstance(argnames, str):
            names.extend([x.strip() for x in argnames.split(",") if x.strip()])
        else:
            names.extend(argnames)
        if len(names) <= 1:
            raise ValueError(
                f"{file}: parameterize({argnames}, ...): expected more than 1 parameter name"
            )
        if len(names) != len(argvalues):
            raise ValueError(
                f"{file}: parameterize({argnames}, ...): expected len(names) == len(values)"
            )
        random_values: list[list[float]] = []
        for i, item in enumerate(argvalues):
            try:
                initial_value, final_value = item
            except ValueError:
                raise ValueError(
                    f"{file}: parameterize({argnames}, ...): expected len(argvalues[{i}]) == 2"
                ) from None
            random_values.append(random_range(initial_value, final_value, int(samples)))
        values = transpose(random_values)
        self = cls(names, values)
        return self

    @staticmethod
    def combine(paramsets: list["ParameterSet"]) -> list[dict[str, Any]]:
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


def random_range(a: float, b: float, n: int) -> list[float]:
    return [random.uniform(a, b) for _ in range(n)]


def transpose(a: list[list[float]]) -> list[list[float]]:
    return [list(_) for _ in zip(*a)]


def append_if_unique(container, item):
    if item not in container:
        container.append(item)


def is_scalar(item: Any) -> bool:
    return isinstance(item, (float, int, str))
