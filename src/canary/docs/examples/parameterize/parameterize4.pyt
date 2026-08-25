# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary
import canary_pyt

canary_pyt.directives.parameterize("a,b", [(1, 1e5), (2, 1e6), (3, 1e7)])
canary_pyt.directives.parameterize("cpus", (4, 8))


def test():
    self = canary.test.instance
    print(f"running test with {self.parameters.a=}, {self.parameters.b=}, {self.parameters.cpus=}")


if __name__ == "__main__":
    sys.exit(test())
