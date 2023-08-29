import argparse

from .common import Command


class Config(Command):
    name = "config"
    description = "Show configuration variable values"

    @property
    def mode(self):
        return "anonymous"

    @staticmethod
    def add_options(parser: argparse.ArgumentParser):
        sp = parser.add_subparsers(dest="subcommand")
        sp.add_parser("show", help="Show the current configuration")

    def pretty_print(self, text: str):
        from pygments import highlight
        from pygments.formatters import TerminalTrueColorFormatter as Formatter
        from pygments.lexers import get_lexer_by_name

        lexer = get_lexer_by_name("yaml")
        print(
            highlight(
                text.strip(), lexer, Formatter(bg="dark", style="monokai", linenos=True)
            )
        )

    def run(self) -> int:
        text = self.session.config.describe()
        if self.session.option.subcommand == "show":
            try:
                self.pretty_print(text)
            except ImportError:
                print(text)
        return 0
