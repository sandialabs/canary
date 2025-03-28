# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import sys

import canary

canary.directives.parameterize("a", [1, 2, 3])
canary.directives.generate_composite_base_case()


def run_parameterized_case(case: canary.TestInstance) -> None:
    # Run the test
    f = f"{case.parameters.a}.txt"
    canary.filesystem.touchp(f)


def analyze_composite_base_case(case: canary.TestMultiInstance) -> None:
    # Analyze the collective
    assert len(case.dependencies) == 3
    for dep in case.dependencies:
        f = os.path.join(dep.working_directory, f"{dep.parameters.a}.txt")
        assert os.path.exists(f)


def main():
    self = canary.get_instance()
    if isinstance(self, canary.TestMultiInstance):
        analyze_composite_base_case(self)
    else:
        run_parameterized_case(self)
    return 0


if __name__ == "__main__":
    sys.exit(main())
