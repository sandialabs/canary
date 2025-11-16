# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys
import time

import canary

canary.directives.keywords("fast")
canary.directives.timeout(2.0)


def test():
    time.sleep(5)


if __name__ == "__main__":
    sys.exit(test())
