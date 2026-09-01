# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary_pyt

canary_pyt.directives.enable(when="options=enable")


def test():
    pass


if __name__ == "__main__":
    sys.exit(test())
