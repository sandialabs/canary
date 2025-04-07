# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.depends_on("ingredients.type=eggs")
canary.directives.depends_on("ingredients.type=ham")


def green_eggs_and_ham() -> int:
    instance = canary.get_instance()
    for dep in instance.dependencies:
        assert dep.family == "ingredients"
        assert dep.parameters.type in ("eggs", "ham")


if __name__ == "__main__":
    sys.exit(green_eggs_and_ham())
