# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Named constants for the three parameter-space sampling strategies.

The :class:`enums` enum and its module-level aliases are used as the ``kind``
argument to :meth:`ParameterSet` factory methods so callers can refer to
strategies by name rather than by magic integer.

Example::

    from _canary.enums import list_parameter_space, centered_parameter_space
    ps = ParameterSet.list_parameter_space(...)
"""

import enum


class enums(enum.Enum):
    """Enumeration of parameter-space sampling strategies.

    Attributes:
        list_parameter_space: Full Cartesian product of all parameter lists.
        centered_parameter_space: One-at-a-time variation around a central point.
        random_parameter_space: Random Monte Carlo sampling of the parameter space.
    """

    list_parameter_space = 0
    centered_parameter_space = 1
    random_parameter_space = 2


list_parameter_space = enums.list_parameter_space
centered_parameter_space = enums.centered_parameter_space
random_parameter_space = enums.random_parameter_space
