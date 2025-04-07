# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.keywords("fast")
canary.directives.xfail()


def test():
    raise canary.TestFailed()


if __name__ == "__main__":
    sys.exit(test())
