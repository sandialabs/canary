from .argparsing import Parser
from .base import Session


class Config(Session):
    """Show configuration variable values"""

    family = "config"

    @property
    def mode(self):
        return self.Mode.ANONYMOUS

    @staticmethod
    def setup_parser(parser: Parser):
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
        text = self.config.describe()
        if self.option.subcommand == "show":
            try:
                self.pretty_print(text)
            except ImportError:
                print(text)
        return 0
