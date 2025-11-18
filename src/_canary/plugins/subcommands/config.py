# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import inspect
import io
import json
import os
from typing import TYPE_CHECKING
from typing import Any

import pluggy
import yaml

from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(ConfigCmd())


class ConfigCmd(CanarySubcommand):
    name = "config"
    description = "Get and set configuration options"

    def setup_parser(self, parser: "Parser") -> None:
        sp = parser.add_subparsers(dest="subcommand")
        p = sp.add_parser(
            "show",
            help="Show current configuration. To show the resource pool, let section=resource_pool",
        )
        p.add_argument(
            "-p",
            "--paths",
            action="store_true",
            default=False,
            dest="file_paths",
            help="Show paths to canary configuration files",
        )
        p.add_argument(
            "--format",
            choices=("json", "yaml"),
            default="yaml",
            help="Print configuration in this format [default: %(default)s]",
        )
        p.add_argument(
            "section",
            nargs="?",
            help="Show only this section.  "
            "The section 'plugin' will print the currently active plugins",
        )
        p = sp.add_parser("set", help="Add to the current configuration")
        g = p.add_mutually_exclusive_group()
        g.add_argument(
            "--local",
            dest="scope",
            default="local",
            const="local",
            action="store_const",
            help="Set the local configuration value",
        )
        g.add_argument(
            "--global",
            dest="scope",
            const="global",
            action="store_const",
            help="Set the local configuration value",
        )
        p.add_argument(
            "path_and_value",
            nargs=2,
            metavar="PATH VALUE",
            help="colon-separated path to config to be set, e.g. 'timeout:default 10.0'",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        from ... import config
        from ...util.json_helper import try_loads

        if args.subcommand == "show":
            show_config(args)
            return 0
        elif args.subcommand == "set":
            path, value = args.path_and_value
            config.write_new(path, try_loads(value), args.scope)
            return 0
        elif args.subcommand is None:
            raise ValueError("canary config: missing required subcommand (choose from show, add)")
        else:
            raise ValueError(f"canary config: unknown subcommand: {args.subcommand}")


def show_config(args: "argparse.Namespace"):
    from ... import config

    text: str
    if args.file_paths:
        global_f = config.get_scope_filename("global")
        local_f = os.path.realpath(config.get_scope_filename("local") or "canary.yaml")
        with io.StringIO() as fp:
            fp.write("configuration paths:\n")
            fp.write(f"  global: {global_f}\n")
            fp.write(f"  local: {local_f}\n")
            print(fp.getvalue())
            return
    if args.section in ("plugins", "plugin"):
        print_active_plugin_descriptions()
        return

    elif args.section in ("resource_pool", "resource-pool", "resources"):
        print(config.pluginmanager.hook.canary_resource_pool_describe())
        return

    else:
        state = config.data
        if args.section is not None:
            state = {args.section: state[args.section]}
        if args.format == "json":
            text = json.dumps({"canary": state}, indent=2)
        else:
            text = yaml.dump({"canary": state}, default_flow_style=False)
    try:
        pretty_print(text, args.format)
    except ImportError:
        print(text)
    return 0


def pretty_print(text: str, fmt: str):
    from pygments import highlight
    from pygments.formatters import (
        TerminalTrueColorFormatter as Formatter,  # ty: ignore[unresolved-import]
    )
    from pygments.lexers import get_lexer_by_name

    lexer = get_lexer_by_name(fmt)
    formatter = Formatter(bg="dark", style="monokai", linenos=True)
    formatted_text = highlight(text.strip(), lexer, formatter)
    print(formatted_text)


def list_name_plugin(pluginmanager: pluggy.PluginManager) -> list[tuple[str, str, str]]:
    plugins: list[tuple[str, str, str]] = []

    for name, plugin in pluginmanager.list_name_plugin():
        file = getfile(plugin)
        namespace = getnamespace(plugin)
        root_namespace = namespace.split(".")[0]
        if root_namespace == "_canary":
            root_namespace = "builtin"
        row = (root_namespace, name, file)
        plugins.append(row)
    return sorted(plugins, key=lambda x: (x[0], x[1]))


def getfile(obj: Any) -> str:
    try:
        return inspect.getfile(obj)
    except TypeError:
        return inspect.getfile(type(obj))


def getnamespace(obj: Any) -> str:
    try:
        return obj.__package__
    except AttributeError:
        return obj.__module__


def print_active_plugin_descriptions() -> None:
    from ... import config

    table: list[tuple[str, str, str]] = []
    widths = [len("Namespace"), len("Name"), 0]
    for namespace, name, file in list_name_plugin(config.pluginmanager):
        row = (namespace, name, file)
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
