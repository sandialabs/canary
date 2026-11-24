# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Work endpoints.  Each runs in the worker child (:mod:`_canary.service.fs.worker`).

Each works through the application layer and returns the result's data.  ``/canary/run``
fills the options object as ``canary run``'s command line would (:func:`options_for`) and
runs it; its data is ``{"exit_code": N}`` (:func:`exit_code`).  ``canary_hpc``'s
``/canary/hpc/run`` does the same with ``canary_hpc.app.run``.
"""

import argparse
import functools
import os
from typing import Any
from typing import Callable

from pydantic import BaseModel

from _canary import config
from _canary.app.pathspec import ScanPathsRequest
from _canary.app.rebaseline import rebaseline as app_rebaseline
from _canary.app.run import run_from_options
from _canary.app.selection import select as app_select
from _canary.config import ConfigError
from _canary.config.argparsing import Parser
from _canary.config.argparsing import make_argument_parser
from _canary.engine.engine import Engine
from _canary.error import SessionTerminated
from _canary.error import StopExecution
from _canary.scanpaths import merge_scanpaths
from _canary.scanpaths import scanpath_from_item
from _canary.util import logging

from .argv import defaults
from .argv import to_options
from .dispatch import Context
from .dispatch import EndpointRegistry
from .dispatch import RequestError
from .models import CollectRequest
from .models import RebaselineRequest
from .models import RunRequest
from .models import SelectRequest
from .roots import check_paths
from .roots import scanned_paths

logger = logging.get_logger(__name__)


@functools.cache
def parser() -> Parser:
    """Canary's parser, with every plugin's commands and options."""
    parser = make_argument_parser()
    config.pluginmanager.hook.canary_addcommand(parser=parser)
    config.pluginmanager.hook.canary_addoption(parser=parser)
    return parser


def options_for(request: BaseModel, *command: str) -> argparse.Namespace:
    """Fill the options object for ``canary COMMAND`` from *request*, and install it.

    The namespace starts from every option's default (plugins' too), takes the request's
    fields through their parser actions, then goes through what ``canary`` does after
    parsing: the ``canary_cmdline_modifyargs`` hook and ``config.set_main_options``.
    ``config.getoption`` then answers as it would for the equivalent command line.  A
    value an action refuses is the caller's mistake (``400``).
    """
    p = parser()
    ns = defaults(p, *command)
    try:
        to_options(request, p.get_subparser("::".join(command)), ns)
    except ValueError as exc:  # an action refused a value (to_options names the field)
        raise RequestError(400, str(exc)) from None
    config.pluginmanager.hook.canary_cmdline_modifyargs(parser=p, args=ns)
    config.set_main_options(ns)
    return ns


def exit_code(session: Callable[[], int]) -> int:
    """Run *session* and return canary's exit code for it.

    The codes ``canary`` gives the exceptions a session ends with (see
    ``_canary.main.console_main``); a configuration error is the caller's (``400``).
    """
    try:
        return session()
    except StopExecution as exc:
        (logger.info if exc.exit_code == 0 else logger.error)(exc.message)
        return exc.exit_code
    except TimeoutError as exc:
        logger.error(exc.args[0] if exc.args else "timed out")
        return 4
    except SessionTerminated as exc:
        logger.error(f"Terminated by {exc.signame}.")
        return 128 + exc.signum
    except ConfigError as exc:
        raise RequestError(400, str(exc)) from None


def check_run_paths(options: argparse.Namespace, ctx: Context) -> None:
    """Refuse a run whose pathspec scans outside the workspace and the allowed roots."""
    request = getattr(options, "request", None)
    if isinstance(request, ScanPathsRequest):
        check_paths(scanned_paths(request.value), ctx)


def run(request: RunRequest, ctx: Context) -> dict[str, Any]:
    """Run tests, as ``canary run`` does: ``{"exit_code": N}``."""
    options = options_for(request, "run")
    check_run_paths(options, ctx)
    return {"exit_code": exit_code(lambda: run_from_options(options))}


def _listed(value: str | None) -> list[str] | None:
    return None if value is None else [value]


def collect(request: CollectRequest, ctx: Context) -> dict[str, Any]:
    """Collect the test cases under *roots* (relative to the request's cwd)."""
    scanpaths: dict[str, list[str]] = {}
    for root in request.roots:
        found = scanpath_from_item(root)
        if found is None:
            raise RequestError(400, f"{root}: no such file or directory")
        merge_scanpaths(scanpaths, found)
    check_paths(scanned_paths(scanpaths), ctx)
    specs = Engine(ctx.workspace).collect(scanpaths, on_options=request.on_options or None)
    return {"collected": len(specs)}


def select(request: SelectRequest, ctx: Context) -> dict[str, Any]:
    """Create the selection *tag* (from all tests, or *from_tag*'s), rename or delete it."""
    workspace = ctx.workspace
    if request.delete:
        if not workspace.is_tag(request.tag):
            raise RequestError(404, f"no selection {request.tag!r}")
        workspace.db.delete_selection(request.tag)
        return {"deleted": request.tag}
    if request.rename_from is not None:
        if not workspace.is_tag(request.rename_from):
            raise RequestError(404, f"no selection {request.rename_from!r}")
        if workspace.is_tag(request.tag):
            raise RequestError(409, f"selection {request.tag!r} already exists")
        workspace.db.rename_selection(request.rename_from, request.tag)
        return {"renamed": request.rename_from, "to": request.tag}
    check_paths([os.path.abspath(p) for p in request.from_root], ctx)
    if request.from_tag is not None and not workspace.is_tag(request.from_tag):
        raise RequestError(404, f"no selection {request.from_tag!r}")
    if request.from_tag is None and workspace.is_tag(request.tag):
        raise RequestError(409, f"selection {request.tag!r} already exists")
    specs = app_select(
        request.tag,
        from_tag=request.from_tag,
        prefixes=request.from_root or None,
        keyword_exprs=_listed(request.keyword),
        parameter_expr=request.parameter,
        owners=_listed(request.owner),
        regex=request.regex,
    )
    return {"tag": request.tag, "selected": len(specs)}


def rebaseline(request: RebaselineRequest, ctx: Context) -> dict[str, Any]:
    """Rebaseline *targets* (job ids or names, or results directories)."""
    check_paths([t for t in request.targets if os.path.exists(t)], ctx)  # results dirs
    count = app_rebaseline(
        request.targets, keyword_exprs=_listed(request.keyword), start=ctx.workspace_root
    )
    return {"rebaselined": count}


def register(registry: EndpointRegistry) -> None:
    registry.register("/canary/run", run, lane="work")
    registry.register("/canary/collect", collect, lane="work")
    registry.register("/canary/select", select, lane="work")
    registry.register("/canary/rebaseline", rebaseline, lane="work")
