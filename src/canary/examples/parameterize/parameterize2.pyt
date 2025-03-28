# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.parameterize("a,b", [(1, 2), (5, 6)])


def test():
    self = canary.test.instance
    print(f"{self.parameters.a=}, {self.parameters.b=}")


if __name__ == "__main__":
    sys.exit(test())
