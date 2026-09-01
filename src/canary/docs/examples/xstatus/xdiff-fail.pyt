# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary_pyt

canary_pyt.directives.keywords("fast")
canary_pyt.directives.xdiff()


def test():
    # This test should fail
    return 0


if __name__ == "__main__":
    sys.exit(test())
