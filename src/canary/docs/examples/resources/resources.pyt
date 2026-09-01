# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary_pyt

canary_pyt.directives.parameterize("cpus,gpus", [(1, 1), (4, 4), (1000, 1000)])


def test():
    pass


if __name__ == "__main__":
    sys.exit(test())
