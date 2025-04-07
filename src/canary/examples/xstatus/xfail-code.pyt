# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.keywords("fast")
canary.directives.xfail(code=23)


def test():
    return 23


if __name__ == "__main__":
    sys.exit(test())
