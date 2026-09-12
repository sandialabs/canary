# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary developer plugin.

This package is **not** shipped with the installed canary package.  It lives in
the ``dev/`` directory at the repository root and is loaded automatically by
:class:`_canary.pluginmanager.CanaryPluginManager` when canary detects it is
running from an editable checkout (a ``.git/`` directory is present next to the
canary source tree) and this ``dev/`` directory exists.

Separating developer tooling here means ``canary check`` / ``canary pre-commit``
are available during development but absent from released wheels.
"""

from _canary.hookspec import hookimpl

from .pre_commit import Check


@hookimpl
def canary_addcommand(parser) -> None:
    """Register the ``check`` / ``pre-commit`` subcommand with canary's CLI."""
    parser.add_command(Check())
