import os
import sys

import nvtest

nvtest.directives.execbase()
nvtest.directives.parameterize("a", [1, 2, 3])


def test():
    # Run the test
    self = nvtest.test.instance
    f = f"{self.parameters.a}.txt"
    nvtest.filesystem.touchp(f)
    return 0


def analyze_parameterized_test():
    # Analyze a single parameterized test
    self = nvtest.test.instance
    f = f"{self.parameters.a}.txt"
    assert os.path.exists(f)


def analyze_base_case():
    # Analyze the collective
    self = nvtest.test.instance
    assert len(self.dependences) == 3
    for dep in self.dependencies:
        f = os.path.join(dep.exec_dir, f"{dep.parameters.a}.txt")
        assert os.path.exists(f)


def main():
    pattern = nvtest.patterns.ExecuteAndAnalyze(
        exec_fn=test, analyze_fn=analyze_parameterized_test, base_fn=analyze_base_case
    )
    pattern.execute()
    return 0


if __name__ == "__main__":
    sys.exit(main())
