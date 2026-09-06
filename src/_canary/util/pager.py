# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Centralized paging helper.

canary paginates several kinds of output (session/job logs, status tables, the
``find`` listings, HPC batch logs).  Historically each subcommand made its own
``pydoc.pager`` / ``rich.Console.pager`` call with slightly different rules for
when to page.  This module unifies that logic behind :func:`page` and
:func:`page_rich` so paging behaves consistently and can be globally disabled.

Paging is disabled when any of the following is true:

1. stdout is not a TTY (piped/redirected output is never paged),
2. the global ``--no-pager`` flag was passed (``config.getoption("no_pager")``),
3. the ``config:no_pager`` config key is set,
4. the ``CANARY_NO_PAGER`` environment variable is set to a truthy value.

The resolution order mirrors :func:`_canary.job.find_cache_dir`: environment
variable first, then config/flag.
"""

import os
import shutil
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import rich.console

_TRUTHY = {"1", "true", "yes", "on"}


def paging_disabled() -> bool:
    """Return True when paging should be suppressed regardless of content size.

    Checks, in order: the ``CANARY_NO_PAGER`` environment variable, the global
    ``--no-pager`` command-line flag, and the ``config:no_pager`` config key.
    """
    raw = os.environ.get("CANARY_NO_PAGER")
    if raw is not None:
        return raw.strip().lower() in _TRUTHY

    # Imported lazily to avoid a circular import at module load time.
    from .. import config

    if config.getoption("no_pager"):
        return True
    if config.get("no_pager"):
        return True
    return False


def should_page(line_count: int | None = None) -> bool:
    """Return True when output should be paged.

    Args:
        line_count: Number of lines the output will occupy.  When provided,
            paging is only requested if the content is taller than the
            terminal.  When ``None``, only the TTY/opt-out checks apply.
    """
    if not sys.stdout.isatty():
        return False
    if paging_disabled():
        return False
    if line_count is not None:
        return line_count > shutil.get_terminal_size().lines
    return True


def page(text: str) -> None:
    """Page *text* through the system pager, or write it directly.

    Paging is used only when stdout is an interactive terminal, paging has not
    been disabled, and the text is taller than the terminal.  Otherwise the
    text is written straight to stdout (with a trailing newline if missing).
    """
    line_count = text.count("\n") + 1
    if should_page(line_count):
        import pydoc

        pydoc.pager(text)
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")


def page_rich(console: "rich.console.Console", renderable: object, line_count: int) -> None:
    """Print a rich *renderable* to *console*, paging when appropriate.

    Args:
        console: The rich console to print with.
        renderable: Any rich-printable object (table, group, columns, ...).
        line_count: Estimated height of the renderable, used to decide whether
            paging is warranted.
    """
    if should_page(line_count):
        with console.pager():
            console.print(renderable)
    else:
        console.print(renderable)
