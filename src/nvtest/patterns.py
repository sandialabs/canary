import argparse
from typing import Callable


def identity(*args, **kwargs):
    ...


def execute_and_analyze(
    *,
    test_fn: Callable = identity,
    verify_fn: Callable = identity,
    analyze_fn: Callable = identity,
):
    """Run the execute/analyze/analyze group test pattern

    Parameters
    ----------
    execute : callable
        Function that ...
    analyze : callable
        Function that ...
    verify : callable
        Function that ...

    Notes
    -----

    """

    def _parser() -> argparse.ArgumentParser:
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

    parser = _parser()
    args, _ = parser.parse_known_args()
    if args.analyze:
        analyze_fn()
    else:
        if not args.execute_analysis_sections:
            test_fn()
        verify_fn()
