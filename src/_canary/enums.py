# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import enum


class enums(enum.Enum):
    list_parameter_space = 0
    centered_parameter_space = 1
    random_parameter_space = 2


list_parameter_space = enums.list_parameter_space
centered_parameter_space = enums.centered_parameter_space
random_parameter_space = enums.random_parameter_space
