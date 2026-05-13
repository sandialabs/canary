# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.depends_on({"job": "willfail", "when": "on_failure"})


def depends_on_willfail() -> int:
    instance = canary.get_instance()
    assert instance.dependencies[0].name == "willfail"
    assert instance.dependencies[0].status.category.name == "FAIL"
    return 0


if __name__ == "__main__":
    sys.exit(depends_on_willfail())
