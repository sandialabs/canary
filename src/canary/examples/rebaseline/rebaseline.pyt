# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import canary

canary.directives.copy("test.base.out")
canary.directives.baseline(src="test.out", dst="test.base.out")


def test():
    with open("test.out", "w") as fh:
        fh.write("Test output")
