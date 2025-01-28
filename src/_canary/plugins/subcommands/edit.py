import argparse
import os

from ... import finder
from ...config.argparsing import Parser
from ...util.editor import editor
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import load_session


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return CanarySubcommand(
        name="edit",
        description="open test files in $EDITOR",
        setup_parser=setup_parser,
        execute=edit,
    )


def setup_parser(parser: "Parser") -> None:
    parser.add_argument("testspec", help="Test file or test case spec")


def edit(args: argparse.Namespace) -> int:
    file = find_file(args.testspec)
    if file is None:
        print(f"{args.testspec}: no matching generator or test case found in {os.getcwd()}")
        return 1
    editor(file)
    return 0


def find_file(testspec: str) -> str | None:
    try:
        generator = finder.find(testspec)
        return generator.file
    except Exception:
        pass
    try:
        session = load_session()
    except Exception:
        return None
    for case in session.cases:
        if case.matches(testspec):
            return case.file
    return None
