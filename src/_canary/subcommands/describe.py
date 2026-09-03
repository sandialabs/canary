# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary describe`` subcommand for printing detailed information about a test generator or job."""

import argparse
from typing import TYPE_CHECKING
from typing import Any

import yaml

from .. import config
from ..collect import Collector
from ..hookspec import hookimpl
from ..util.rich import colorize
from ..util.serialize import serialize
from ..workspace import Workspace
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..generator import AbstractTestGenerator
    from ..job import Job
    from ..jobspec import JobSpec


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Describe())


class Describe(CanarySubcommand):
    """Print YAML-formatted metadata for a test generator file or a workspace job/spec."""

    name = "describe"
    description = "Print information about a job file, job"

    def setup_parser(self, parser: "Parser") -> None:
        """Register the ``testspec`` positional and ``-o`` option-enable flag."""
        parser.add_argument(
            "-o",
            dest="on_options",
            default=None,
            metavar="option",
            action="append",
            help="Turn option(s) on, such as '-o dbg' or '-o intel'",
        )
        parser.add_argument("testspec", help="Job file or job spec")

    def execute(self, args: argparse.Namespace) -> int:
        """Describe the generator or job identified by ``args.testspec`` and return 0."""
        collector = Collector()
        config.pluginmanager.hook.canary_collectstart(collector=collector)
        for type in collector.types:
            if gen := type.factory(args.testspec):
                describe_generator(gen, on_options=args.on_options)
                return 0

        # could be a job in the test session?
        workspace = Workspace.load()
        try:
            job_or_spec = workspace.find(job=args.testspec)
        except:
            job_or_spec = workspace.find(spec=args.testspec)
        describe_job(job_or_spec)
        return 0


def describe_generator(file: "AbstractTestGenerator", on_options: list[str] | None = None) -> None:
    """Print the colorized description of a test generator, optionally with options enabled."""
    description = file.describe(on_options=on_options)
    print(colorize(description.rstrip()))


def dump(data: dict[str, Any]) -> str:
    """Serialize *data* to a YAML string with block-style output."""
    return yaml.dump(data, default_flow_style=False)


def describe_job(job: "Job | JobSpec", indent: str = "") -> None:
    """Pretty-print syntax-highlighted YAML metadata for *job* or *spec*."""
    from pygments import highlight
    from pygments.formatters import (
        TerminalTrueColorFormatter as Formatter,  # ty: ignore[unresolved-import]
    )
    from pygments.lexers import get_lexer_by_name

    state = serialize(job)
    text = dump({"name": job.display_name(), **state})
    lexer = get_lexer_by_name("yaml")
    formatter = Formatter(bg="dark", style="monokai")
    formatted_text = highlight(text.strip(), lexer, formatter)
    print(formatted_text)
