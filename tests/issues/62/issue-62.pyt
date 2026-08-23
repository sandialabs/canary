# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary_pyt

canary_pyt.directives.enable(False, when='parameters="Letter=c"')
canary_pyt.directives.keywords("fast", when='parameters="Letter=a"')
canary_pyt.directives.keywords("enable_test")
canary_pyt.directives.parameterize("Letter", ("a", "b", "c"))


def main():
    case = canary.get_instance()
    print("Letter = ", case.parameters["Letter"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
