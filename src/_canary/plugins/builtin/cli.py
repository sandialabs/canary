# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import importlib.util
import shlex
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING
from typing import Generator

from ...hookspec import hookimpl
from ...third_party.monkeypatch import monkeypatch

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl(wrapper=True)
def canary_addoption(parser: "Parser") -> Generator[None, None, None]:
    with monkeypatch.context() as mp:
        mp.setattr(parser, "add_argument", parser.add_plugin_argument)
        mp.setattr(parser, "add_argument_group", parser.add_plugin_argument_group)
        yield


@hookimpl(trylast=True)
def canary_cmdline_parse(parser: "Parser", args: list[str]) -> argparse.Namespace:
    """Expand command aliases and parse Canary command-line arguments.

    Looks for the first non-option argument in ``args`` and treats it as a
    potential Canary command alias. If the command matches an entry in the
    configured ``aliases`` mapping, the alias is expanded in place before
    delegating to ``parser.parse_args``.

    Alias strings are parsed as shell-like command fragments using
    ``shlex.split``. Template substitutions are performed with
    ``string.Template.safe_substitute``. The following template variables are
    supported:

    * ``$@``: Expands to the remaining command-line arguments after the alias.
      This is normalized internally to ``${args}`` before template expansion.
    * ``$canary``: Expands to the installed Canary package prefix.

    Unlike git's ordinary aliases, additional command-line arguments are not
    appended automatically after alias expansion. They are inserted only when
    the alias explicitly contains ``$@``.

    Examples:
        Given an alias such as::

            aliases:
              rwe: run -w $@ $canary/examples

        The command::

            canary rwe --my-args --are-these --and this

        is expanded before parsing to approximately::

            canary run -w --my-args --are-these --and this /path/to/canary/examples

    Args:
        parser: The Canary argument parser.
        args: Command-line arguments to parse. This list is modified in place
            if an alias expansion is performed.

    Returns:
        The parsed argparse namespace.

    Raises:
        RuntimeError: If an alias uses ``$canary`` and the Canary package
            prefix cannot be determined.
    """
    from ... import config

    if aliases := config.get("aliases"):
        canary_prefix = get_canary_prefix()
        for i, arg in enumerate(args):
            if arg.startswith("-"):
                continue
            alias = aliases.get(arg)
            if not alias:
                break
            extra_args = args[i + 1 :]
            alias = alias.replace("$@", "${args}")
            expanded = Template(alias).safe_substitute(
                args=shlex.join(extra_args), canary=shlex.quote(str(canary_prefix))
            )
            args[i:] = shlex.split(expanded)
            break
    return parser.parse_args(args)


def get_canary_prefix() -> Path | None:
    spec = importlib.util.find_spec("canary")
    if spec is not None:
        if spec.submodule_search_locations:
            return Path(next(iter(spec.submodule_search_locations))).resolve()
        if spec.origin:
            return Path(spec.origin).resolve().parent
    return None
