# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import re
import sys
from io import StringIO

from rich.console import Console
from rich.text import Text

# Mapping from color arguments to values for logging.set_color
color_when_values = {"always": True, "auto": None, "never": False}
_force_color: bool | None = color_when_values.get(os.getenv("COLOR_WHEN", "auto"))

# Reuse consoles to avoid overhead
_COLOR_CONSOLE = Console(
    file=StringIO(),
    force_terminal=True,
    color_system="truecolor",
    width=10_000,
    legacy_windows=False,
)

_PLAIN_CONSOLE = Console(
    file=StringIO(),
    force_terminal=False,
    color_system=None,
    width=10_000,
)


def set_color_when(when):
    """Set when color should be applied.  Options are:

    * True or 'always': always print color
    * False or 'never': never print color
    * None or 'auto': only print color if sys.stderr is a tty.
    """
    global _force_color
    if when in (True, "always"):
        os.environ["COLOR_WHEN"] = "always"
    elif when in (False, "never"):
        os.environ["COLOR_WHEN"] = "never"
    elif when in (None, "auto"):
        os.environ["COLOR_WHEN"] = "auto"
    _force_color = _color_when_value(when)


def _color_when_value(when) -> bool | None:
    """Raise a ValueError for an invalid color setting.

    Valid values are 'always', 'never', and 'auto', or equivalently,
    True, False, and None.
    """
    if when in color_when_values:
        return color_when_values[when]
    elif when not in color_when_values.values():
        raise ValueError("Invalid color setting: %s" % when)
    return when


def colorize(message: str, *, color: bool | None = None) -> str:
    """
    Render a Rich-markup string to:
      - ANSI-colored text if color=True
      - Plain text if color=False

    The returned value is a string suitable for logging or file output.
    """
    if not message:
        return message

    use_color: bool
    if color is not None:
        use_color = color
    elif _force_color is not None:
        use_color = _force_color
    else:
        use_color = sys.stdin.isatty()

    # Reset buffers
    console = _COLOR_CONSOLE if use_color else _PLAIN_CONSOLE
    buffer = console.file
    buffer.seek(0)
    buffer.truncate(0)

    # Parse markup safely
    text = Text.from_markup(message)

    console.print(text, end="")
    return buffer.getvalue()  # type: ignore


def clen(string):
    """Return the length of a string, excluding ansi color sequences."""
    return len(re.sub(r"\033[^m]*m", "", string))


def cstrip(string):
    """Strip ansi color sequences from string"""
    return re.sub(r"\033[^m]*m", "", string)


def cextra(string):
    """Length of extra color characters in a string"""
    return len("".join(re.findall(r"\033[^m]*m", string)))


def bold(arg: str) -> str:
    if os.getenv("COLOR_WHEN", "auto") == "never":
        return f"**{arg}**"
    return colorize("[bold]%s[/]" % arg)


def code(arg: str) -> str:
    if os.getenv("COLOR_WHEN", "auto") == "never":
        return f"``{arg}``"
    return colorize("[bold]%s[/]" % arg)
