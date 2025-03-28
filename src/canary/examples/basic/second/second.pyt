# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.keywords("basic", "second")
canary.directives.link("add.py")


def test():
    print("Verifying that 2 + 3 = 5")
    add = canary.Executable("./add.py")
    result = add("2", "3", stdout=str)
    assert int(result.get_output()) == 5, "Bummer, test failed."
    print("Test passed!")


if __name__ == "__main__":
    sys.exit(test())
