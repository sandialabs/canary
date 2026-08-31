# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary_pyt

canary_pyt.directives.keywords("fast")
canary_pyt.directives.xfail(code=23)


def test():
    return 23


if __name__ == "__main__":
    sys.exit(test())
