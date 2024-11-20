import os
import sys

import nvtest

nvtest.directives.parameterize("a", [1, 2, 3])
nvtest.directives.generate_composite_base_case()


def run_parameterized_case(case: nvtest.TestInstance) -> None:
    # Run the test
    f = f"{case.parameters.a}.txt"
    nvtest.filesystem.touchp(f)


def analyze_composite_base_case(case: nvtest.TestMultiInstance) -> None:
    # Analyze the collective
    assert len(case.dependencies) == 3
    for dep in case.dependencies:
        f = os.path.join(dep.exec_dir, f"{dep.parameters.a}.txt")
        assert os.path.exists(f)


def main():
    self = nvtest.get_instance()
    if isinstance(self, nvtest.TestMultiInstance):
        analyze_composite_base_case(self)
    else:
        run_parameterized_case(self)
    return 0


if __name__ == "__main__":
    sys.exit(main())
