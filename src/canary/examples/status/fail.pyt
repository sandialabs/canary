# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.keywords("fast")


def test():
    raise canary.TestFailed()


if __name__ == "__main__":
    sys.exit(test())
