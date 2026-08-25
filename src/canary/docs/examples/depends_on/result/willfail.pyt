# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys


def willfail() -> int:
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(willfail())
