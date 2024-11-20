import os
import sys

import nvtest

nvtest.directives.parameterize("a", [1, 2, 3])
nvtest.directives.stages("analyze")


def run(case: nvtest.TestInstance) -> None:
    # Run the test
    nvtest.logging.info("running the very expensive 'run' stage")
    f = f"{case.parameters.a}.txt"
    nvtest.filesystem.touchp(f)
    analyze(case)


def analyze(case: nvtest.TestInstance) -> None:
    # Analyze a single parameterized test
    nvtest.logging.info("running the relatively cheap 'analyze' stage")
    f = f"{case.parameters.a}.txt"
    assert os.path.exists(f)


def main():
    parser = nvtest.make_argument_parser()
    args = parser.parse_args()
    self = nvtest.get_instance()
    if args.stage == "analyze":
        analyze(self)
    elif args.stage == "run":
        run(self)
    else:
        nvtest.logging.warning(f"unknown execution stage {args.stage=}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
