from typing import TYPE_CHECKING

from _nvtest.config import Config

if TYPE_CHECKING:
    import argparse

    from _nvtest.config.argparsing import Parser


description = "Show configuration variable values"


def setup_parser(parser: "Parser"):
    sp = parser.add_subparsers(dest="subcommand")
    sp.add_parser("show", help="Show the current configuration")


def pretty_print(text: str):
    from pygments import highlight
    from pygments.formatters import TerminalTrueColorFormatter as Formatter
    from pygments.lexers import get_lexer_by_name

    lexer = get_lexer_by_name("yaml")
    print(
        highlight(
            text.strip(), lexer, Formatter(bg="dark", style="monokai", linenos=True)
        )
    )


def config(config: "Config", args: "argparse.Namespace") -> int:
    text = config.describe()
    if args.subcommand == "show":
        try:
            pretty_print(text)
        except ImportError:
            print(text)
    return 0
