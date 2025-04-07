# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.parameterize("a", (1, 4))


def test():
    self = canary.get_instance()
    print(f"{self.parameters.a}")


if __name__ == "__main__":
    sys.exit(test())
