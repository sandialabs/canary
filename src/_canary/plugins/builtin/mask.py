# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import re
from typing import TYPE_CHECKING

from ... import when
from ...third_party.color import colorize
from ...util import filesystem
from ...util import graph
from ...util import logging
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...test.case import TestCase


@hookimpl(tryfirst=True)
def canary_testsuite_mask(
    cases: list["TestCase"],
    keyword_exprs: list[str] | None,
    parameter_expr: str | None,
    owners: set[str] | None,
    regex: str | None,
    case_specs: list[str] | None,
    start: str | None,
) -> None:
    """Filter test cases (mask test cases that don't meet a specific criteria)

    Args:
      keyword_exprs: Include those tests matching this keyword expressions
      parameter_expr: Include those tests matching this parameter expression
      start: The starting directory the python session was invoked in
      case_specs: Include those tests matching these specs

    """
    from ... import config

    ctx = logging.context(colorize("@*{Masking} test cases based on filtering criteria"))
    ctx.start()
    rx: re.Pattern | None = None
    if regex is not None:
        logging.warning("Regular expression search can be slow for large test suites")
        rx = re.compile(regex)

    no_filter_criteria = all(_ is None for _ in (keyword_exprs, parameter_expr, owners, regex))

    if start is not None:
        if not os.path.isabs(start):
            start = os.path.join(config.session.work_tree, start)  # type: ignore
        start = os.path.normpath(start)

    owners = set(owners or [])
    order = graph.static_order_ix(cases)
    for i in order:
        case = cases[i]

        if case.masked():
            continue

        if start is not None and isrel(case.execfile, start):
            # won't mask
            continue

        if start is not None and not isrel(case.working_directory, start):
            logging.debug(f"{case}: {case.working_directory=} but {start=}")
            case.mask = "Unreachable from start directory"
            continue

        if case_specs is not None:
            if not any(case.matches(case_spec) for case_spec in case_specs):
                expr = ",".join(case_specs)
                case.mask = colorize("testspec expression @*{%s} did not match" % expr)
            continue

        try:
            config.resource_pool.satisfiable(case.required_resources())
        except config.ResourceUnsatisfiable as e:
            case.mask = colorize("@*{ResourceUnsatisfiable}(%r)" % e.args[0])
            continue

        if owners and not owners.intersection(case.owners):
            case.mask = colorize("not owned by @*{%r}" % case.owners)
            continue

        if keyword_exprs is not None:
            kwds = set(case.keywords)
            kwds.update(case.implicit_keywords)
            kwd_all = contains_any(("__all__", ":all:"), keyword_exprs)
            if not kwd_all:
                for keyword_expr in keyword_exprs:
                    match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                    if not match:
                        case.mask = colorize(
                            "keyword expression @*{%r} did not match" % keyword_expr
                        )
                        break
                if case.masked():
                    continue

        if parameter_expr:
            match = when.when(
                {"parameters": parameter_expr},
                parameters=case.parameters | case.implicit_parameters,
            )
            if not match:
                case.mask = colorize("parameter expression @*{%s} did not match" % parameter_expr)
                continue

        if case.dependencies:
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
                    case.mask = colorize("@*{re.search(%r) is None} evaluated to @*g{True}" % regex)
                    continue

        # If we got this far and the case is not masked, only mask it if no filtering criteria were
        # specified
        if no_filter_criteria and not case.status.satisfies(("created", "pending", "ready")):
            case.mask = f"previous status {case.status.value!r} is not 'ready'"

    for i in order:
        config.plugin_manager.hook.canary_testcase_modify(case=cases[i])

    ctx.stop()


def isrel(path1: str | None, path2: str) -> bool:
    if path1 is None:
        return False
    return os.path.abspath(path1).startswith(os.path.abspath(path2))


def contains_any(elements: tuple[str, ...], test_elements: list[str]) -> bool:
    return any(element in test_elements for element in elements)
