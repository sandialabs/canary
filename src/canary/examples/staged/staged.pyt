import os
import sys

import canary

canary.directives.parameterize("cpus", [1, 4, 8])
canary.directives.stages("analyze", "plot", when="parameters='cpus=1'")


def run(case: canary.TestInstance) -> None:
    """Run the test"""
    canary.logging.info("running the very expensive 'run' stage")
    with open("run.txt", "w") as fh:
        fh.write("success")


def analyze(case: canary.TestInstance) -> None:
    """Analyze a single parameterized test"""
    canary.logging.info("running the relatively cheap 'analyze' stage")
    if not open("run.txt").read() == "success":
        raise canary.TestFailed(f"{case}: 'run' stage did not successfully complete")
    with open("analyze.txt", "w") as fh:
        fh.write("success")


def plot(case: canary.TestInstance) -> None:
    """Plot the results after the analysis stage"""
    canary.logging.info("plotting results during the 'plot' stage")
    if not os.path.exists("analyze.txt"):
        raise ValueError(f"{case}: analyze.txt not found, did you run the 'analyze' stage?")
    if not open("analyze.txt").read() == "success":
        raise canary.TestFailed(f"{case}: 'analyze' stage did not successfully complete")
    with open("plot.txt", "w") as fh:
        fh.write("success")


def main():
    parser = canary.make_argument_parser()
    args = parser.parse_args()
    self = canary.get_instance()
    if args.stage == "analyze":
        analyze(self)
    elif args.stage == "plot":
        plot(self)
    elif args.stage == "run":
        run(self)
        analyze(self)
    else:
        canary.logging.warning(f"unknown execution stage {args.stage=}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
