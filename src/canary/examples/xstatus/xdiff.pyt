# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary
import canary_pyt

canary_pyt.directives.keywords("fast")
canary_pyt.directives.xdiff()


def test():
    raise canary.TestDiffed()


if __name__ == "__main__":
    sys.exit(test())
