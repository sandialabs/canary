# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.depends_on("a")


def depends_on_a():
    instance = canary.get_instance()
    assert len(instance.dependencies) == 1
    assert instance.dependencies[0].name == "a"


if __name__ == "__main__":
    sys.exit(depends_on_a())
