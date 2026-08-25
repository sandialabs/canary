# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys
import time

import canary_pyt

canary_pyt.directives.timeout(2.0)


def test() -> int:
    time.sleep(5)
    return 0


if __name__ == "__main__":
    sys.exit(test())
