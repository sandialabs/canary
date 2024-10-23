import json
import os
import sys

import nvtest

nvtest.directives.analyze()
nvtest.directives.keywords("centered_space")
nvtest.directives.parameterize(
    "a,b", [(0, 5, 2), (0, 1, 2)], type=nvtest.enums.centered_parameter_space
)


def test():
    self = nvtest.get_instance()
    if self.analyze:
        return analyze()
    with open("output.json", "w") as fh:
        json.dump({"a": self.parameters.a, "b": self.parameters.b}, fh)
    return 0


def analyze():
    self = nvtest.get_instance()
    parameters = {}
    for dep in self.dependencies:
        with open(os.path.join(dep.exec_dir, "output.json")) as fh:
            data = json.load(fh)
            parameters.setdefault("a", []).append(data["a"])
            parameters.setdefault("b", []).append(data["b"])
    assert parameters == {"a": [0, -10, -5, 5, 10, 0, 0, 0, 0], "b": [0, 0, 0, 0, 0, -2, -1, 1, 2]}


if __name__ == "__main__":
    sys.exit(test())
