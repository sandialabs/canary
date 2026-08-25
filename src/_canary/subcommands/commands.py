# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Emit Canary command reference information.

By default, ``canary commands`` prints a compact list of registered Canary
subcommands and their descriptions. With ``--expand``, it prints the full
argparse help for each command. With ``--style=rst`` and ``-d DEST``, it writes
reStructuredText command reference files suitable for committed Sphinx
documentation.
"""

import argparse
import dataclasses
import re
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Literal

from .. import config
from ..config.argparsing import make_argument_parser
from ..hookspec import hookimpl
from ..util.filesystem import mkdirp
from ..util.rich import set_color_when
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


COPYRIGHT = """\
.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

"""

Style = Literal["text", "rst"]


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    """Register the ``commands`` subcommand."""
    parser.add_command(Commands())


@dataclasses.dataclass(frozen=True)
class CommandDoc:
    """Documentation data extracted from one argparse subcommand parser."""

    name: str
    parser: argparse.ArgumentParser
    summary: str

    @property
    def title(self) -> str:
        """Return the display title for this command."""
        return f"canary {self.name}"

    @property
    def label(self) -> str:
        """Return the stable Sphinx label for this command."""
        return f"commands.{self.name}"

    @property
    def filename(self) -> str:
        """Return the RST filename for a multi-page command reference."""
        return f"commands.{self.name}.rst"

    @property
    def help_text(self) -> str:
        """Return full argparse help text for this command."""
        return self.parser.format_help().rstrip()


class Commands(CanarySubcommand):
    """Emit command inventory and command reference documentation."""

    name = "commands"
    description = "List or generate reference documentation for Canary commands"

    def setup_parser(self, parser: "Parser") -> None:
        """Configure command-line options for ``canary commands``."""
        parser.add_argument(
            "--expand",
            action="store_true",
            default=False,
            help="Include full argparse help for every command",
        )
        parser.add_argument(
            "--style",
            choices=("text", "rst"),
            default="text",
            help="Output style [default: %(default)s]",
        )
        parser.add_argument(
            "--multi-page",
            action="store_true",
            default=False,
            help="With --style=rst and -d, write one page per command",
        )
        parser.add_argument(
            "-d",
            "--dest",
            default=None,
            help="Destination directory. If omitted, output is written to stdout",
        )
        parser.add_argument(
            "--wipe",
            action="store_true",
            default=False,
            help="Remove existing generated command reference files before writing",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print the files that would be generated without writing them",
        )

    def execute(self, args: argparse.Namespace) -> int:
        """Run the command inventory/reference emitter."""
        set_color_when("never")

        style: Style = args.style

        emit_commands(
            style=style,
            expand=bool(args.expand),
            multi_page=bool(args.multi_page),
            dest=None if args.dest is None else Path(args.dest),
            wipe=bool(args.wipe),
            dry_run=bool(args.dry_run),
        )
        return 0


def emit_commands(
    *,
    style: Style = "text",
    expand: bool = False,
    multi_page: bool = False,
    dest: Path | None = None,
    wipe: bool = False,
    dry_run: bool = False,
) -> None:
    """Emit command documentation to stdout or files."""
    if multi_page and style != "rst":
        raise ValueError("--multi-page is only valid with --style=rst")

    if multi_page and dest is None:
        raise ValueError("--multi-page requires -d/--dest")

    if wipe and dest is None:
        raise ValueError("--wipe requires -d/--dest")

    if dry_run and dest is None:
        raise ValueError("--dry-run requires -d/--dest")

    parser = build_documented_parser()
    commands = discover_command_docs(parser)

    if dest is None:
        text = render_stdout(style=style, expand=expand, commands=commands)
        print(text, end="" if text.endswith("\n") else "\n")
        return

    outputs = plan_outputs(
        style=style, expand=expand, multi_page=multi_page, dest=dest, commands=commands
    )

    if dry_run:
        print("Would generate:")
        for path, _ in outputs:
            print(path)
        if wipe:
            print()
            print("Would remove existing generated command reference files matching:")
            for pattern in wipe_patterns(style=style):
                print(dest.resolve() / pattern)
        return

    if wipe and dest.exists():
        wipe_generated_files(dest=dest, style=style)

    mkdirp(dest)

    for path, text in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def build_documented_parser() -> "Parser":
    """Build a Canary parser with all command and option hooks applied."""
    parser = make_argument_parser(all=True)
    parser.add_main_epilog(parser)
    config.pluginmanager.hook.canary_addcommand(parser=parser)
    config.pluginmanager.hook.canary_addoption(parser=parser)
    return parser


def discover_command_docs(parser: argparse.ArgumentParser) -> list[CommandDoc]:
    """Return canonical command docs discovered from the parser."""
    subparsers = find_subparsers_action(parser)
    if subparsers is None:
        return []

    summaries = command_summaries(subparsers)
    docs: list[CommandDoc] = []

    for name in sorted(subparsers.choices):
        subparser = subparsers.choices[name]
        if not isinstance(subparser, argparse.ArgumentParser):
            continue

        # Prefer the help text shown in the parent command list. Fall back to
        # the subparser description if needed.
        summary = summaries.get(name) or first_line(subparser.description or "")
        docs.append(CommandDoc(name=name, parser=subparser, summary=summary))

    return docs


def find_subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    """Return the top-level argparse subparsers action, if present."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def command_summaries(subparsers: argparse._SubParsersAction) -> dict[str, str]:
    """Return command help summaries keyed by command name."""
    summaries: dict[str, str] = {}

    for action in getattr(subparsers, "_choices_actions", []):
        name = getattr(action, "dest", None)
        help_text = getattr(action, "help", None)

        if not name or help_text == argparse.SUPPRESS:
            continue

        summaries[str(name)] = "" if help_text is None else str(help_text)

    return summaries


def first_line(text: str) -> str:
    """Return the first non-empty line of text."""
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def render_stdout(*, style: Style, expand: bool, commands: list[CommandDoc]) -> str:
    """Render command information for stdout."""
    if style == "text":
        return render_expanded_text(commands) if expand else render_summary_text(commands)
    return render_expanded_rst(commands) if expand else render_summary_rst(commands)


def plan_outputs(
    *, style: Style, expand: bool, multi_page: bool, dest: Path, commands: list[CommandDoc]
) -> list[tuple[Path, str]]:
    """Return files and contents that should be generated."""
    dest = dest.resolve()

    if style == "text":
        text = render_expanded_text(commands) if expand else render_summary_text(commands)
        return [(dest / "commands.txt", text)]

    if multi_page:
        outputs: list[tuple[Path, str]] = [
            (dest / "commands.rst", render_multipage_index_rst(commands))
        ]
        for command in commands:
            outputs.append((dest / command.filename, render_command_page_rst(command)))
        return outputs

    text = render_expanded_rst(commands) if expand else render_summary_rst(commands)
    return [(dest / "commands.rst", text)]


def wipe_patterns(*, style: Style) -> list[str]:
    """Return generated-file glob patterns for a style."""
    if style == "rst":
        return ["commands*.rst"]
    return ["commands.txt"]


def wipe_generated_files(*, dest: Path, style: Style) -> None:
    """Remove generated command reference files for a style."""
    for pattern in wipe_patterns(style=style):
        for path in dest.glob(pattern):
            if path.is_file() or path.is_symlink():
                path.unlink()


def render_summary_text(commands: list[CommandDoc]) -> str:
    """Render a compact plain-text command list."""
    if not commands:
        return "Canary commands\n\n  No commands registered.\n"

    width = max(len(command.name) for command in commands)
    lines = ["Canary commands", ""]

    for command in commands:
        summary = command.summary or ""
        lines.append(f"  {command.name:<{width}}  {summary}")

    lines.append("")
    return "\n".join(lines)


def render_expanded_text(commands: list[CommandDoc]) -> str:
    """Render full argparse help for every command as plain text."""
    lines: list[str] = []

    for i, command in enumerate(commands):
        if i:
            lines.append("")
        lines.append(command.title)
        lines.append("=" * len(command.title))
        lines.append("")
        lines.append(command.help_text)

    lines.append("")
    return "\n".join(lines)


def render_summary_rst(commands: list[CommandDoc]) -> str:
    """Render a compact single-page RST command summary."""
    lines = [
        COPYRIGHT,
        "Command Reference",
        "=================",
        "",
        "The following commands are registered with Canary.",
        "",
    ]

    if not commands:
        lines.extend(["No commands are registered.", ""])
        return "\n".join(lines)

    lines.extend(
        [
            ".. list-table::",
            "   :header-rows: 1",
            "   :widths: 25 75",
            "",
            "   * - Command",
            "     - Description",
        ]
    )

    for command in commands:
        lines.extend([f"   * - ``canary {command.name}``", f"     - {rst_inline(command.summary)}"])

    lines.append("")
    return "\n".join(lines)


def render_expanded_rst(commands: list[CommandDoc]) -> str:
    """Render a single-page RST command reference with full help for each command."""
    lines = [
        COPYRIGHT,
        "Command Reference",
        "=================",
        "",
        "The following sections are generated from Canary's command-line parser.",
        "",
    ]

    for command in commands:
        lines.extend(render_command_section_rst(command, level="-"))

    return "\n".join(lines)


def render_multipage_index_rst(commands: list[CommandDoc]) -> str:
    """Render the multi-page RST command index."""
    lines = [
        COPYRIGHT,
        ".. _commands:",
        "",
        "Command Reference",
        "=================",
        "",
        "The following pages are generated from Canary's command-line parser.",
        "",
    ]

    if commands:
        lines.extend(
            [
                ".. list-table::",
                "   :header-rows: 1",
                "   :widths: 25 75",
                "",
                "   * - Command",
                "     - Description",
            ]
        )

        for command in commands:
            lines.extend(
                [
                    f"   * - :ref:`canary {command.name} <{command.label}>`",
                    f"     - {rst_inline(command.summary)}",
                ]
            )

        lines.extend(["", ".. toctree::", "   :maxdepth: 1", "   :hidden:", ""])

        for command in commands:
            lines.append(f"   {command.filename.removesuffix('.rst')}")

        lines.append("")
    else:
        lines.extend(["No commands are registered.", ""])

    return "\n".join(lines)


def render_command_page_rst(command: CommandDoc) -> str:
    """Render one full RST page for a command."""
    lines = [COPYRIGHT, f".. _{command.label}:", "", command.title, "=" * len(command.title), ""]

    if command.summary:
        lines.extend([rst_paragraph(command.summary), ""])

    lines.extend(
        [
            ".. code-block:: console",
            "",
            *indent_lines(command.help_text.splitlines(), prefix="   "),
            "",
        ]
    )

    return "\n".join(lines)


def render_command_section_rst(command: CommandDoc, *, level: str) -> list[str]:
    """Render a full RST section for a command."""
    lines = [f".. _{command.label}:", "", command.title, level * len(command.title), ""]

    if command.summary:
        lines.extend([rst_paragraph(command.summary), ""])

    lines.extend(
        [
            ".. code-block:: console",
            "",
            *indent_lines(command.help_text.splitlines(), prefix="   "),
            "",
        ]
    )

    return lines


def indent_lines(lines: list[str], *, prefix: str) -> list[str]:
    """Indent lines for inclusion in a reStructuredText code block."""
    return [prefix + line if line else prefix for line in lines]


def rst_inline(text: str) -> str:
    """Return text suitable for simple inline use in RST tables."""
    text = text.strip().replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text or " "


def rst_paragraph(text: str) -> str:
    """Return normalized paragraph text for RST output."""
    text = text.strip()
    return re.sub(r"\n{3,}", "\n\n", text)
