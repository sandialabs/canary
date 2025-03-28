# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.depends_on("breakfast.dish=spam")


def lunch() -> int:
    instance = canary.get_instance()
    assert instance.dependencies[0].family == "breakfast"
    assert instance.dependencies[0].parameters.dish == "spam"


if __name__ == "__main__":
    sys.exit(lunch())
