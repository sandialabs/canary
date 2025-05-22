# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import inspect
import io
import json
import os
from typing import TYPE_CHECKING

import yaml

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
    description = "Print configuration variable values"

    def setup_parser(self, parser: "Parser") -> None:
        sp = parser.add_subparsers(dest="subcommand")
        p = sp.add_parser("show", help="Show the current configuration")
        p.add_argument(
            "-p",
            "--paths",
            action="store_true",
            default=False,
            help="Show paths to canary configuration files",
        )
        p.add_argument(
            "--format",
            choices=("json", "yaml"),
            default="yaml",
            help="Print configuration in this format [default: %(default)s]",
        )
        p.add_argument(
            "--pretty",
            action="store_true",
            default=False,
            help="Pretty-print the contents of the config in the given format [default: False]",
        )
        p.add_argument(
            "section",
            nargs="?",
            help="Show only this section.  "
            "The section 'plugin' will print the currently active plugins",
        )
        p = sp.add_parser("add", help="Add to the current configuration")
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

        if root := find_work_tree(os.getcwd()):
            load_session(root=root)
        if args.subcommand == "show":
            show_config(args)
            return 0
        elif args.subcommand == "add":
            config.save(args.path, scope=args.scope)
            return 0
        elif args.subcommand is None:
            raise ValueError("canary config: missing required subcommand (choose from show, add)")
        else:
            raise ValueError(f"canary config: unknown subcommand: {args.subcommand}")


def show_config(args: "argparse.Namespace"):
    from ... import config

    text: str
    if args.paths:
        global_f = config.config_file("global")
        local_f = os.path.realpath(config.config_file("local") or "canary.yaml")
        with io.StringIO() as fp:
            fp.write("configuration paths:\n")
            fp.write(f"  global: {global_f}\n")
            fp.write(f"  local: {local_f}\n")
            print(fp.getvalue())
            return
    if args.section in ("plugins", "plugin"):
        print_active_plugin_descriptions()
        return
    else:
        state = config.getstate(pretty=True)
        if args.section is not None:
            state = {args.section: state[args.section]}
        if args.format == "json":
            text = json.dumps(state, indent=2)
        else:
            text = yaml.dump(state, default_flow_style=False)
    try:
        if args.pretty:
            pretty_print(text, args.format)
        else:
            print(text)
    except ImportError:
        print(text)
    return 0


def pretty_print(text: str, fmt: str):
    from pygments import highlight
    from pygments.formatters import TerminalTrueColorFormatter as Formatter
    from pygments.lexers import get_lexer_by_name

    lexer = get_lexer_by_name(fmt)
    formatter = Formatter(bg="dark", style="monokai", linenos=True)
    formatted_text = highlight(text.strip(), lexer, formatter)
    print(formatted_text)


def print_active_plugin_descriptions() -> None:
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
    for backend in hpc_connect.backends().values():  # type: ignore
        try:
            row = ("hpc_connect", backend.name, inspect.getfile(backend))
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
    print(fp.getvalue())
