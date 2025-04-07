# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.parameterize("a", (1, 4))
canary.directives.parameterize("b", (1.0e5, 1.0e6, 1.0e7))


def test():
    self = canary.test.instance
    print(f"running test with {self.parameters.a=} and {self.parameters.b=}")


if __name__ == "__main__":
    sys.exit(test())
