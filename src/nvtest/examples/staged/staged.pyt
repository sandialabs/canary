import os
import sys

import nvtest

nvtest.directives.parameterize("cpus", [1, 4, 8])
nvtest.directives.stages("analyze", "plot")


def run(case: nvtest.TestInstance) -> None:
    """Run the test"""
    nvtest.logging.info("running the very expensive 'run' stage")
    with open("run.txt", "w") as fh:
        fh.write("success")


def analyze(case: nvtest.TestInstance) -> None:
    """Analyze a single parameterized test"""
    nvtest.logging.info("running the relatively cheap 'analyze' stage")
    if not open("run.txt").read() == "success":
        raise nvtest.TestFailed(f"{case}: 'run' stage did not successfully complete")
    with open("analyze.txt", "w") as fh:
        fh.write("success")


def plot(case: nvtest.TestInstance) -> None:
    """Plot the results after the analysis stage"""
    nvtest.logging.info("plotting results during the 'plot' stage")
    if not os.path.exists("analyze.txt"):
        raise ValueError(f"{case}: analyze.txt not found, did you run the 'analyze' stage?")
    if not open("analyze.txt").read() == "success":
        raise nvtest.TestFailed(f"{case}: 'analyze' stage did not successfully complete")
    with open("plot.txt", "w") as fh:
        fh.write("success")


def main():
    parser = nvtest.make_argument_parser()
    args = parser.parse_args()
    self = nvtest.get_instance()
    if args.stage == "analyze":
        analyze(self)
    elif args.stage == "plot":
        plot(self)
    elif args.stage == "run":
        run(self)
        analyze(self)
    else:
        nvtest.logging.warning(f"unknown execution stage {args.stage=}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
