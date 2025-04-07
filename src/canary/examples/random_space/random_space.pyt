# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.parameterize(
    "a,b", [(0, 5), (6, 10)], samples=4, type=canary.random_parameter_space
)


def test():
    self = canary.get_instance()
    print(f"a={self.parameters.a}, b={self.parameters.b}")
    return 0


if __name__ == "__main__":
    sys.exit(test())
