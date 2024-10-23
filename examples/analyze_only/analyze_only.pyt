import json
import os
import sys

import nvtest

nvtest.directives.execbase()
nvtest.directives.parameterize("np", (1, 2))
nvtest.directives.parameterize("a,b", [(1, 2), (2, 3), (4, 5)])


def test():
    self = nvtest.get_instance()
    if self.multicase:
        return base()
    with open("output.json", "w") as fh:
        json.dump({"np": self.parameters.np, "a": self.parameters.a, "b": self.parameters.b}, fh)


def base():
    self = nvtest.get_instance()
    for dep in self.dependencies:
        file = os.path.join(dep.exec_dir, "output.json")
        with open(file) as fh:
            parameters = json.load(fh)
            assert parameters["np"] == dep.parameters.np
            assert parameters["a"] == dep.parameters.a
            assert parameters["b"] == dep.parameters.b
    assert self.parameters.np == (1, 1, 1, 2, 2, 2)
    assert self.parameters.a == (1, 2, 4, 1, 2, 4)
    assert self.parameters.b == (2, 3, 5, 2, 3, 5)
    assert self.parameters[("np", "a", "b")] == (
        (1, 1, 2),
        (1, 2, 3),
        (1, 4, 5),
        (2, 1, 2),
        (2, 2, 3),
        (2, 4, 5),
    )
    for i, dep in enumerate(self.dependencies):
        x = (dep.parameters["np"], dep.parameters["a"], dep.parameters["b"])
        y = self.parameters[("np", "a", "b")][i]
        assert x == y


if __name__ == "__main__":
    sys.exit(test())
