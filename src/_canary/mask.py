# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import re
import time
from typing import TYPE_CHECKING

from . import when
from .util import filesystem
from .util import graph
from .util import logging

if TYPE_CHECKING:
    from .testcase import TestCase
    from .config.config import Config


logger = logging.get_logger(__name__)


def mask_testcases(
    cases: list["TestCase"],
    config: "Config",
    keyword_exprs: list[str] | None,
    parameter_expr: str | None,
    owners: set[str] | None,
    regex: str | None,
    start: str | None,
    ignore_dependencies: bool,
) -> None:
    """Filter test cases (mask test cases that don't meet a specific criteria)

    Args:
      keyword_exprs: Include those tests matching this keyword expressions
      parameter_expr: Include those tests matching this parameter expression
      start: The starting directory the python session was invoked in

    """
    msg = "@*{Masking} test cases based on filtering criteria"
    created = time.monotonic()
    logger.log(logging.INFO, msg, extra={"end": "..."})
    rx: re.Pattern | None = None
    try:
        if regex is not None:
            logger.warning("Regular expression search can be slow for large test suites")
            rx = re.compile(regex)

        no_filter_criteria = all(_ is None for _ in (keyword_exprs, parameter_expr, owners, regex))

        if start is not None:
            if not os.path.isabs(start):
                start = os.path.join(config.get("session:work_tree"), start)  # type: ignore
            start = os.path.normpath(start)

        owners = set(owners or [])
        order = graph.static_order_ix(cases)
        for i in order:
            case = cases[i]

            if case.masked():
                continue

            if start is not None and no_filter_criteria and isrel(case.working_directory, start):
                # won't mask
                continue

            if start is not None and not isrel(case.working_directory, start):
                logger.debug(f"{case}: {case.working_directory=} but {start=}")
                case.mask = "Unreachable from start directory"
                continue

            try:
                check = config.pluginmanager.hook.canary_resource_pool_accommodates(case=case)
            except Exception as e:
                case.mask = "@*{%s}(%r)" % (e.__class__.__name__, e.args[0])
                continue
            else:
                if not check:
                    case.mask = check.reason
                    continue

            if owners and not owners.intersection(case.owners):
                case.mask = "not owned by @*{%r}" % case.owners
                continue

            if keyword_exprs is not None:
                kwds = set(case.keywords)
                kwds.update(case.implicit_keywords)
                kwd_all = contains_any(("__all__", ":all:"), keyword_exprs)
                if not kwd_all:
                    for keyword_expr in keyword_exprs:
                        match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                        if not match:
                            case.mask = "keyword expression @*{%r} did not match" % keyword_expr
                            break
                    if case.masked():
                        continue

            if parameter_expr:
                match = when.when(
                    {"parameters": parameter_expr},
                    parameters=case.parameters | case.implicit_parameters,
                )
                if not match:
                    case.mask = "parameter expression @*{%s} did not match" % parameter_expr
                    continue

            if case.dependencies and not ignore_dependencies:
                flags = case.dep_condition_flags()
                if any([flag == "wont_run" for flag in flags]):
                    case.mask = "one or more dependencies not satisfied"
                    continue

            if rx is not None:
                if not filesystem.grep(rx, case.file):
                    for asset in case.assets:
                        if os.path.isfile(asset.src) and filesystem.grep(rx, asset.src):
                            break
                    else:
                        case.mask = "@*{re.search(%r) is None} evaluated to @*g{True}" % regex
                        continue

            # If we got this far and the case is not masked, only mask it if no filtering criteria were
            # specified
            if no_filter_criteria and not case.status.satisfies(("created", "pending", "ready")):
                case.mask = f"previous status {case.status.value!r} is not 'ready'"
    except Exception:
        state = "failed"
        raise
    else:
        state = "done"
    finally:
        end = "... %s (%.2fs.)\n" % (state, time.monotonic() - created)
        extra = {"end": end, "rewind": True}
        logger.log(logging.INFO, msg, extra=extra)


def isrel(path1: str | None, path2: str) -> bool:
    if path1 is None:
        return False
    return os.path.abspath(path1).startswith(os.path.abspath(path2))


def contains_any(elements: tuple[str, ...], test_elements: list[str]) -> bool:
    return any(element in test_elements for element in elements)
