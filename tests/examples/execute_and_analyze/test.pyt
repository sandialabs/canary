import os
import sys
import nvtest

nvtest.directives.analyze()
nvtest.directives.parameterize("a", [1, 2, 3])


def test():
    # Run the test
    self = nvtest.test.instance
    f = f'{self.parameters.a}.txt'
    nvtest.filesystem.touchp(f)
    return 0


def analyze_parameterized_test():
    # Analyze a single parameterized test
    self = nvtest.test.instance
    f = f'{self.parameters.a}.txt'
    assert os.path.exists(f)


def analyze():
    # Analyze the collective
    self = nvtest.test.instance
    for dep in self.dependencies:
        f = os.path.join(dep.exec_dir, f'{dep.parameters.a}.txt')
        assert os.path.exists(f)


def main():
    pattern = nvtest.patterns.ExecuteAndAnalyze(
        test_fn=test, verify_fn=analyze_parameterized_test, analyze_fn=analyze
    )
    pattern()
    return 0


if __name__ == '__main__':
    sys.exit(main())
