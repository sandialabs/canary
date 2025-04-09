# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import os
import sys

import canary

canary.directives.analyze()
canary.directives.keywords("centered_space")
canary.directives.parameterize("a,b", [(0, 5, 2), (0, 1, 2)], type=canary.centered_parameter_space)


def test():
    self = canary.get_instance()
    if self.analyze:
        return analyze()
    with open("output.json", "w") as fh:
        json.dump({"a": self.parameters.a, "b": self.parameters.b}, fh)
    return 0


def analyze():
    self = canary.get_instance()
    parameters = {}
    for dep in self.dependencies:
        with open(os.path.join(dep.working_directory, "output.json")) as fh:
            data = json.load(fh)
            parameters.setdefault("a", []).append(data["a"])
            parameters.setdefault("b", []).append(data["b"])
    assert parameters == {"a": [0, -10, -5, 5, 10, 0, 0, 0, 0], "b": [0, 0, 0, 0, 0, -2, -1, 1, 2]}


if __name__ == "__main__":
    sys.exit(test())
