import argparse
from typing import Callable
from typing import Optional


def identity(*args, **kwargs): ...


class ExecuteAndAnalyze:
    """Run the execute/analyze/analyze group test pattern

    Parameters
    ----------
    test_fn : callable
        Function that executes the test
    verify_fn : callable
        Function that executes the parameterized test verification
    analyze_fn : callable
        Function that executes the group analysis

    """

    def __init__(
        self,
        *,
        test_fn: Callable = identity,
        verify_fn: Callable = identity,
        analyze_fn: Callable = identity,
    ) -> None:
        self.run_test = test_fn
        self.analyze_parameterized_test = verify_fn
        self.analyze_group = analyze_fn

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
            "--execute-analysis-sections",
            action="store_true",
            help=(
                "Skip the parameterized execute function but do run the"
                "verify function associated with the parameterized execute function"
            ),
        )
        return parser

    def __call__(self, args: Optional[argparse.Namespace] = None) -> None:
        return self.execute()

    def execute(self, args: Optional[argparse.Namespace] = None) -> None:
        if args is None:
            parser = self.make_parser()
            args, _ = parser.parse_known_args()
        if args.analyze:
            self.analyze_group()
        else:
            if not args.execute_analysis_sections:
                self.run_test()
            self.analyze_parameterized_test()
