# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import sys

import canary

canary.directives.keywords("baz")


def test():
    self = canary.get_instance()
    assert self.timeout == 240, f"{self.timeout=}"


if __name__ == "__main__":
    sys.exit(test())
