# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary_pyt

canary_pyt.directives.cpus(4)


def test():
    pass


if __name__ == "__main__":
    sys.exit(test())
