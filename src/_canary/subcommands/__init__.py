# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary CLI subcommand registry and documentation utilities.

All built-in subcommands are imported here and exposed via ``plugins`` for
discovery by the plugin manager.  Public symbols: ``plugins``, ``make_commands_docs``.
"""

from . import check
from . import collect
from . import config
from . import describe
from . import docs
from . import edit
from . import exec
from . import fetch
from . import find
from . import gc
from . import help
from . import info
from . import init
from . import learn
from . import location
from . import log
from . import query
from . import rebaseline
from . import report
from . import rm
from . import run
from . import select
from . import selection
from . import status
from . import tree
from . import view

plugins = [
    check,
    collect,
    config,
    describe,
    docs,
    edit,
    exec,
    fetch,
    find,
    gc,
    help,
    info,
    init,
    learn,
    location,
    log,
    query,
    rebaseline,
    report,
    rm,
    run,
    select,
    selection,
    status,
    tree,
    view,
]


def make_commands_docs(prefix: str) -> None:
    """Write RST documentation for all registered CLI subcommands.

    Args:
        prefix: Destination directory under which a ``commands/`` sub-directory
            is created containing one RST file per subcommand.
    """
    import os

    from .. import config
    from ..config.argparsing import make_argument_parser
    from ..third_party import argparsewriter as aw
    from ..util.rich import set_color_when

    set_color_when("never")
    dest = os.path.join(prefix, "commands")
    parser = make_argument_parser()
    config.pluginmanager.hook.canary_addcommand(parser=parser)
    writer = aw.ArgparseMultiRstWriter(parser.prog, dest)
    writer.write(parser)
