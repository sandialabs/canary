import argparse
import os

import _nvtest.config as _config
from _nvtest.config.argparsing import Parser
from _nvtest.session import Session
from _nvtest.command import Command


class Config(Command):
    @property
    def description(self) -> str:
        return "Show configuration variable values"

    def setup_parser(self, parser: Parser):
        sp = parser.add_subparsers(dest="subcommand")
        p = sp.add_parser("show", help="Show the current configuration")
        p.add_argument("section", nargs="?", help="Show only this section")
        p = sp.add_parser("add", help="Show the current configuration")
        p.add_argument(
            "--scope",
            choices=("local", "global", "session"),
            default="local",
            help="Configuration scope",
        )
        p.add_argument(
            "path",
            help="colon-separated path to config to be set, e.g. 'config:debug:true'",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        if Session.find_root(os.getcwd()):
            Session(os.getcwd(), mode="r")
        if args.subcommand == "show":
            text = _config.describe(section=args.section)
            try:
                if "NVTEST_MAKE_DOCS" in os.environ:
                    print(text)
                else:
                    pretty_print(text)
            except ImportError:
                print(text)
            return 0
        elif args.subcommand == "add":
            _config.add(args.path, scope=args.scope)
            file = _config.config_file(args.scope)
            assert file is not None
            with open(file, "w") as fh:
                _config.save(fh, scope=args.scope)
        elif args.command is None:
            raise ValueError("nvtest config: missing required subcommand (choose from show, add)")
        else:
            raise ValueError(f"nvtest config: unknown subcommand: {args.subcommand}")
        return 1


def pretty_print(text: str):
    from pygments import highlight
    from pygments.formatters import TerminalTrueColorFormatter as Formatter
    from pygments.lexers import get_lexer_by_name

    lexer = get_lexer_by_name("yaml")
    formatter = Formatter(bg="dark", style="monokai", linenos=True)
    formatted_text = highlight(text.strip(), lexer, formatter)
    print(formatted_text)
