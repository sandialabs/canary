# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.keywords("fast")
canary.directives.xdiff()


def test():
    raise canary.TestDiffed()


if __name__ == "__main__":
    sys.exit(test())
