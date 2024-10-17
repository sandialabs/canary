import argparse
import inspect
import io
import os
from typing import Any

import _nvtest.config as _config
import _nvtest.plugin as plugin
from _nvtest.command import Command
from _nvtest.config.argparsing import Parser
from _nvtest.session import Session


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
        do_pretty_print: bool = "NVTEST_MAKE_DOCS" in os.environ
        if Session.find_root(os.getcwd()):
            Session(os.getcwd(), mode="r")
        if args.subcommand == "show":
            text: str
            if args.section in ("plugins", "plugin"):
                text = get_active_plugin_description()
                do_pretty_print = False
            else:
                text = _config.describe(section=args.section)
            try:
                if do_pretty_print:
                    pretty_print(text)
                else:
                    print(text)
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


def _get_plugin_info(p: Any) -> tuple[str, str, str]:
    namespace = getattr(p, "namespace", p.__module__.split(".")[0])
    if namespace == "_nvtest":
        namespace = "builtin"
    name = getattr(p, "name", p.__name__)
    file = getattr(p, "file", inspect.getfile(p))
    return (namespace, name, file)


def get_active_plugin_description() -> str:
    table: list[tuple[str, str, str]] = []
    widths = [len("Namespace"), len("Name"), 0]
    for hook in plugin.plugins():
        row = _get_plugin_info(hook)
        for i, ri in enumerate(row):
            widths[i] = max(widths[i], len(ri))
        table.append(row)
    for gen_type in plugin.generators():
        row = _get_plugin_info(gen_type)
        for i, ri in enumerate(row):
            widths[i] = max(widths[i], len(ri))
        table.append(row)
    for runner_type in plugin.runners():
        row = _get_plugin_info(runner_type)
        for i, ri in enumerate(row):
            widths[i] = max(widths[i], len(ri))
        table.append(row)
    rows = sorted(table, key=lambda _: _[0])
    fp = io.StringIO()
    fp.write("{0:{1}s}  {2:{3}s}  File\n".format("Namespace", widths[0], "Name", widths[1]))
    fp.write("{0}  {1}  {2}\n".format("=" * widths[0], "=" * widths[1], "=" * widths[2]))
    for row in rows:
        fp.write(
            "{0:{1}s}  {2:{3}s}  {4:{5}s}\n".format(
                row[0], widths[0], row[1], widths[1], row[2], widths[2]
            )
        )
    return fp.getvalue()
