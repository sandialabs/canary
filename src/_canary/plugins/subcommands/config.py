# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import inspect
import io
import os
from typing import TYPE_CHECKING

from ...util.filesystem import find_work_tree
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import load_session

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return ConfigCmd()


class ConfigCmd(CanarySubcommand):
    name = "config"
    description = "Show configuration variable values"

    def setup_parser(self, parser: "Parser") -> None:
        sp = parser.add_subparsers(dest="subcommand")
        p = sp.add_parser("show", help="Show the current configuration")
        p.add_argument(
            "-p",
            action="store_true",
            default=False,
            help="Show paths to canary configuration files",
        )
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
        from ... import config

        do_pretty_print: bool = "CANARY_MAKE_DOCS" not in os.environ
        if root := find_work_tree(os.getcwd()):
            load_session(root=root)
        if args.subcommand == "show":
            text: str
            if args.p:
                import yaml

                paths = {}
                paths["global"] = config.config_file("global")
                paths["local"] = os.path.relpath(config.config_file("local") or "canary.yaml")
                with io.StringIO() as fp:
                    yaml.dump({"configuration paths": paths}, fp, default_flow_style=False)
                    text = fp.getvalue()
                    do_pretty_print = False
            elif args.section in ("plugins", "plugin"):
                text = get_active_plugin_description()
                do_pretty_print = False
            else:
                text = config.describe(section=args.section)
            try:
                if do_pretty_print:
                    pretty_print(text)
                else:
                    print(text)
            except ImportError:
                print(text)
            return 0
        elif args.subcommand == "add":
            config.save(args.path, scope=args.scope)
        elif args.command is None:
            raise ValueError("canary config: missing required subcommand (choose from show, add)")
        else:
            raise ValueError(f"canary config: unknown subcommand: {args.subcommand}")
        return 1


def pretty_print(text: str):
    from pygments import highlight
    from pygments.formatters import TerminalTrueColorFormatter as Formatter
    from pygments.lexers import get_lexer_by_name

    lexer = get_lexer_by_name("yaml")
    formatter = Formatter(bg="dark", style="monokai", linenos=True)
    formatted_text = highlight(text.strip(), lexer, formatter)
    print(formatted_text)


def get_active_plugin_description() -> str:
    import hpc_connect

    from ... import config

    table: list[tuple[str, str, str]] = []
    widths = [len("Namespace"), len("Name"), 0]
    for name, plugin in config.plugin_manager.list_name_plugin():
        file = inspect.getfile(plugin)  # type: ignore
        namespace = plugin.__package__.split(".")[0]  # type: ignore
        if namespace == "_canary":
            namespace = "builtin"
        row = (namespace, name, file)
        for i, ri in enumerate(row):
            widths[i] = max(widths[i], len(ri))
        table.append(row)
    for scheduler_type in hpc_connect.schedulers().values():  # type: ignore
        try:
            row = ("hpc_connect", scheduler_type.name, inspect.getfile(scheduler_type))
        except Exception:
            continue
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
