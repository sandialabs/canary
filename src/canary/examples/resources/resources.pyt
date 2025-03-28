# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary
from _canary.util.rprobe import cpu_count

canary.directives.parameterize("cpus,gpus", [(1, 1), (4, 4), (2 * cpu_count(), 2 * cpu_count())])


def test():
    pass


if __name__ == "__main__":
    sys.exit(test())
