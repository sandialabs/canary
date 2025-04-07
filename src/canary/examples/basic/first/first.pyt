# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.keywords("basic", "first")


def add(a: int, b: int) -> int:
    return a + b


def test():
    assert add(3, 2) == 5


if __name__ == "__main__":
    sys.exit(test())
