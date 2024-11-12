import argparse
from typing import Callable


def identity(*args, **kwargs): ...


class ExecuteAndAnalyze:
    """Run the execute/analyze/analyze group test pattern

    Args:
      exec_fn: Function that executes the test
      analyze_fn: Function that analyzes the parameterized test
      base_fn: Function that executes the base case

    """

    def __init__(
        self,
        *,
        exec_fn: Callable = identity,
        analyze_fn: Callable = identity,
        base_fn: Callable = identity,
    ) -> None:
        self.run_test = exec_fn
        self.analyze_parameterized_test = analyze_fn
        self.analyze_base_case = base_fn

    @staticmethod
    def make_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--analyze",
            action="store_true",
            help="Run a final cross parameter analyze function",
        )
        group.add_argument(
            "--base",
            action="store_true",
            help="Run a final cross parameter analyze function",
        )
        group.add_argument(
            "--execute-analysis-sections",
            action="store_true",
            help=(
                "Skip the parameterized execute function but do run the"
                "verify function associated with the parameterized execute function"
            ),
        )
        return parser

    def __call__(self, args: argparse.Namespace | None = None) -> None:
        return self.execute()

    def execute(self, args: argparse.Namespace | None = None) -> None:
        if args is None:
            parser = self.make_parser()
            args, _ = parser.parse_known_args()
        if args.analyze:
            self.analyze_base_case()
        elif args.base:
            self.analyze_base_case()
        else:
            if not args.execute_analysis_sections:
                self.run_test()
            self.analyze_parameterized_test()
