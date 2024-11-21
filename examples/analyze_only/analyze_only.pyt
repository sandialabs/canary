import json
import os
import sys

import nvtest

nvtest.directives.generate_composite_base_case()
nvtest.directives.parameterize("np", (1, 2))
nvtest.directives.parameterize("a,b", [(1, 2), (2, 3), (4, 5)])


def test():
    self = nvtest.get_instance()
    if isinstance(self, nvtest.TestMultiInstance):
        return composite_base_case(self)
    else:
        return single_test_case(self)


def single_test_case(case: nvtest.TestInstance):
    with open("output.json", "w") as fh:
        json.dump({"np": case.parameters.np, "a": case.parameters.a, "b": case.parameters.b}, fh)


def composite_base_case(case: nvtest.TestMultiInstance):
    for dep in case.dependencies:
        file = os.path.join(dep.working_directory, "output.json")
        with open(file) as fh:
            parameters = json.load(fh)
            assert parameters["np"] == dep.parameters.np
            assert parameters["a"] == dep.parameters.a
            assert parameters["b"] == dep.parameters.b
    assert case.parameters.np == (1, 1, 1, 2, 2, 2)
    assert case.parameters.a == (1, 2, 4, 1, 2, 4)
    assert case.parameters.b == (2, 3, 5, 2, 3, 5)
    assert case.parameters[("np", "a", "b")] == (
        (1, 1, 2),
        (1, 2, 3),
        (1, 4, 5),
        (2, 1, 2),
        (2, 2, 3),
        (2, 4, 5),
    )
    for i, dep in enumerate(case.dependencies):
        x = (dep.parameters["np"], dep.parameters["a"], dep.parameters["b"])
        y = case.parameters[("np", "a", "b")][i]
        assert x == y


if __name__ == "__main__":
    sys.exit(test())
