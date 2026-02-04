# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.keywords("basic")


def add(a: int, b: int) -> int:
    return a + b


def test():
    with open("/opt/alegranevada/team/x/macos/src/canary/fooo.txt", "w") as fh:
        import os

        self = canary.get_instance()
        fh.write(f"{os.getcwd()}\n")
        fh.write(str(self))

    assert add(3, 2) == 5


if __name__ == "__main__":
    sys.exit(test())
