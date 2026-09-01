# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import canary_pyt

canary_pyt.directives.copy("test.base.out")
canary_pyt.directives.baseline(src="test.out", dst="test.base.out")


def test():
    with open("test.out", "w") as fh:
        fh.write("Test output")
