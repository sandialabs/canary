# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import Callable


def identity(*args, **kwargs): ...


class ExecuteAndAnalyze:
    """Run the execute/analyze/analyze group test pattern

    Args:
      test_fn: Function that executes the test
      verify_fn: Function that analyzes the parameterized test
      analyze_fn: Function that executes the base case

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
        self.analyze_base_case = analyze_fn

    @staticmethod
    def make_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--analyze",
            "--base",
            dest="analyze_composite_base",
            action="store_true",
            help="Run a final composite base case's analyze function",
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
        if args.analyze_composite_base:
            self.analyze_base_case()
        else:
            if not args.execute_analysis_sections:
                self.run_test()
            self.analyze_parameterized_test()
