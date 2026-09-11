# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary_pyt

canary_pyt.directives.owners("canary-developers")


def test():
    return 0


if __name__ == "__main__":
    sys.exit(test())
