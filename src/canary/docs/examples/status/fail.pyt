# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary
import canary_pyt

canary_pyt.directives.keywords("fast")


def test():
    raise canary.TestFailed()


if __name__ == "__main__":
    sys.exit(test())
