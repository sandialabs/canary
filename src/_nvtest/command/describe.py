from typing import TYPE_CHECKING

from .. import finder
from .common import add_mark_arguments
from .common import add_resource_arguments

if TYPE_CHECKING:
    import argparse

    from _nvtest.config.argparsing import Parser


description = "Print information about a test"


def setup_parser(parser: "Parser"):
    add_mark_arguments(parser)
    add_resource_arguments(parser)
    parser.add_argument("file", help="Test file")


def describe(args: "argparse.Namespace") -> int:
    file = finder.find(args.file)
    description = file.describe(
        keyword_expr=args.keyword_expr, on_options=args.on_options, rh=args.rh
    )
    print(description.rstrip())
    return 0
