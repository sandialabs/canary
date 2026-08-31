# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary
import canary_pyt

canary_pyt.directives.depends_on("ingredients.type=*")


def blt() -> int:
    instance = canary.get_instance()
    for dep in instance.dependencies:
        assert dep.family == "ingredients"
    return 0


if __name__ == "__main__":
    sys.exit(blt())
