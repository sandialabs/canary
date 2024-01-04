from typing import TYPE_CHECKING

import _nvtest.config

from ..util import tty

if TYPE_CHECKING:
    import argparse

    from _nvtest.config.argparsing import Parser


description = "Show configuration variable values"


def setup_parser(parser: "Parser"):
    sp = parser.add_subparsers(dest="subcommand")
    p = sp.add_parser("show", help="Show the current configuration")
    p.add_argument("section", nargs="?", help="Show only this section")
    p = sp.add_parser("add", help="Show the current configuration")
    p.add_argument(
        "--scope",
        choices=("local", "global"),
        default="local",
        help="Configuration scope",
    )
    p.add_argument(
        "path",
        help="colon-separated path to config to be set, e.g. 'config:debug:true'",
    )


def pretty_print(text: str):
    from pygments import highlight
    from pygments.formatters import TerminalTrueColorFormatter as Formatter
    from pygments.lexers import get_lexer_by_name

    lexer = get_lexer_by_name("yaml")
    formatter = Formatter(bg="dark", style="monokai", linenos=True)
    formatted_text = highlight(text.strip(), lexer, formatter)
    print(formatted_text)


def config(args: "argparse.Namespace") -> int:
    if args.subcommand == "show":
        text = _nvtest.config.describe(section=args.section)
        try:
            pretty_print(text)
        except ImportError:
            print(text)
        return 0
    elif args.subcommand == "add":
        _nvtest.config.add(args.path, scope=args.scope)
        file = _nvtest.config.config_file(args.scope)
        assert file is not None
        with open(file, "w") as fh:
            _nvtest.config.dump(fh, scope=args.scope)
    else:
        tty.die(f"nvtest config: unknown subcommand: {args.subcommand}")
    return 1
