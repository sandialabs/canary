# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import canary

canary.directives.enable(False, when='parameters="Letter=c"')
canary.directives.keywords("fast", when='parameters="Letter=a"')
canary.directives.keywords("enable_test")
canary.directives.parameterize("Letter", ("a", "b", "c"))


def main():
    case = canary.get_instance()
    print("Letter = ", case.parameters["Letter"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
