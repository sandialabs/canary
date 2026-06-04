# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import canary

canary.directives.copy("copy.txt")
canary.directives.link("link.txt")
canary.directives.copy("${NAME}.*.txt")


def test():
    assert os.path.exists("copy.txt") and not os.path.islink("copy.txt")
    assert os.path.exists("link.txt") and os.path.islink("link.txt")
    assert os.path.exists("copy_and_link.1.txt") and not os.path.islink("copy_and_link.1.txt")
    assert os.path.exists("copy_and_link.2.txt") and not os.path.islink("copy_and_link.2.txt")


if __name__ == "__main__":
    test()
