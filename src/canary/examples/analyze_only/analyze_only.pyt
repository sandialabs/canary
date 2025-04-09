# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import os
import sys

import canary

canary.directives.generate_composite_base_case()
canary.directives.parameterize("cpus", (1, 2))
canary.directives.parameterize("a,b", [(1, 2), (2, 3), (4, 5)])


def test():
    self = canary.get_instance()
    if isinstance(self, canary.TestMultiInstance):
        return composite_base_case(self)
    else:
        return single_test_case(self)


def single_test_case(case: canary.TestInstance):
    with open("output.json", "w") as fh:
        json.dump(
            {"cpus": case.parameters.cpus, "a": case.parameters.a, "b": case.parameters.b}, fh
        )


def composite_base_case(case: canary.TestMultiInstance):
    for dep in case.dependencies:
        file = os.path.join(dep.working_directory, "output.json")
        with open(file) as fh:
            parameters = json.load(fh)
            assert parameters["cpus"] == dep.parameters.cpus
            assert parameters["a"] == dep.parameters.a
            assert parameters["b"] == dep.parameters.b
    assert case.parameters.cpus == (1, 1, 1, 2, 2, 2)
    assert case.parameters.a == (1, 2, 4, 1, 2, 4)
    assert case.parameters.b == (2, 3, 5, 2, 3, 5)
    assert case.parameters[("cpus", "a", "b")] == (
        (1, 1, 2),
        (1, 2, 3),
        (1, 4, 5),
        (2, 1, 2),
        (2, 2, 3),
        (2, 4, 5),
    )
    for i, dep in enumerate(case.dependencies):
        x = (dep.parameters["cpus"], dep.parameters["a"], dep.parameters["b"])
        y = case.parameters[("cpus", "a", "b")][i]
        assert x == y


if __name__ == "__main__":
    sys.exit(test())
