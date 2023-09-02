from .argparsing import ArgumentParser

default_timeout = 60 * 60


def add_mark_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "-k",
        dest="keyword_expr",
        default="",
        metavar="EXPRESSION",
        help="Only run tests matching given keyword expression. "
        "For example: -k 'key1 and not key2'.",
    )
    parser.add_argument(
        "-o",
        dest="on_options",
        default=[],
        metavar="OPTION",
        action="append",
        help="Turn option(s) on, such as '-o dbg' or '-o intel'",
    )
