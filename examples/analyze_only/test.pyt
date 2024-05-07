import json
import os
import sys

import nvtest


nvtest.directives.analyze()
nvtest.directives.parameterize("a,b", [(1, 2), (2, 3), (4, 5)])


def test():
    self = nvtest.get_instance()
    if self.analyze:
        return analyze()
    with open("output.json", "w") as fh:
        json.dump({"a": self.parameters.a, "b": self.parameters.b}, fh)


def analyze():
    self = nvtest.get_instance()
    for dep in self.dependencies:
        file = os.path.join(dep.exec_dir, "output.json")
        with open(file) as fh:
            parameters = json.load(fh)
            assert parameters["a"] == dep.parameters.a
            assert parameters["b"] == dep.parameters.b


if __name__ == "__main__":
    sys.exit(test())
