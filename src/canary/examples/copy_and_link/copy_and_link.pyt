# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import canary

canary.directives.copy("copy.txt")
canary.directives.link("link.txt")


def test():
    assert os.path.exists("copy.txt") and not os.path.islink("copy.txt")
    assert os.path.exists("link.txt") and os.path.islink("link.txt")
