# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import re
import time
from graphlib import TopologicalSorter
from typing import TYPE_CHECKING
from typing import Generator

from ... import config
from ... import when
from ...util import filesystem
from ...util import logging
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...testspec import ResolvedSpec


logger = logging.get_logger(__name__)


@hookimpl(wrapper=True)
def canary_testsuite_mask(
    specs: list["ResolvedSpec"],
    keyword_exprs: list[str] | None,
    parameter_expr: str | None,
    owners: set[str] | None,
    regex: str | None,
    ids: list[str] | None,
) -> Generator[None, None, None]:
    """Filter test cases (mask test cases that don't meet a specific criteria)

    Args:
      keyword_exprs: Include those tests matching this keyword expressions
      parameter_expr: Include those tests matching this parameter expression
      start: The starting directory the python session was invoked in
      case_specs: Include those tests matching these specs

    """
    for spec in specs:
        config.pluginmanager.hook.canary_testspec_mask(spec=spec)
    yield
    propagate_masks(specs)


@hookimpl(specname="canary_testsuite_mask")
def apply_masks(
    specs: list["ResolvedSpec"],
    keyword_exprs: list[str] | None,
    parameter_expr: str | None,
    owners: set[str] | None,
    regex: str | None,
    ids: list[str] | None,
) -> None:
    """Filter test specs (mask test specs that don't meet a specific criteria)

    Args:
      keyword_exprs: Include those tests matching this keyword expressions
      parameter_expr: Include those tests matching this parameter expression
      ids: Include those tests matching these ids

    """
    msg = "@*{Masking} test specs based on filtering criteria"

    start = time.monotonic()
    logger.log(logging.INFO, msg, extra={"end": "..."})

    rx: re.Pattern | None = None
    if regex is not None:
        logger.warning("Regular expression search can be slow for large test suites")
        rx = re.compile(regex)

    owners = set(owners or [])

    # Get an index of sorted order
    map: dict[str, int] = {d.id: i for i, d in enumerate(specs)}
    graph: dict[int, int] = {map[s.id]: [map[_.id] for _ in s.dependencies] for s in specs}
    ts = TopologicalSorter(graph)
    order = list(ts.static_order())

    try:
        for i in order:
            spec = specs[i]

            if spec.mask:
                continue

            if ids is not None:
                if not any(spec.matches(id) for id in ids):
                    expr = ",".join(ids)
                    spec.mask = "testspec expression @*{%s} did not match" % expr
                continue

            try:
                check = config.pluginmanager.hook.canary_resource_pool_accommodates(case=spec)
            except Exception as e:
                spec.mask = "@*{%s}(%r)" % (e.__class__.__name__, e.args[0])
                continue
            else:
                if not check:
                    spec.mask = check.reason
                    continue

            if owners and not owners.intersection(spec.owners or []):
                spec.mask = "not owned by @*{%r}" % spec.owners
                continue

            if keyword_exprs is not None:
                kwds = set(spec.keywords)
                kwds.update(spec.implicit_keywords)
                kwd_all = contains_any(("__all__", ":all:"), keyword_exprs)
                if not kwd_all:
                    for keyword_expr in keyword_exprs:
                        match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                        if not match:
                            spec.mask = "keyword expression @*{%r} did not match" % keyword_expr
                            break
                    if spec.mask:
                        continue

            if parameter_expr:
                match = when.when(
                    {"parameters": parameter_expr},
                    parameters=spec.parameters | spec.implicit_parameters,
                )
                if not match:
                    spec.mask = "parameter expression @*{%s} did not match" % parameter_expr
                    continue

            if rx is not None:
                if not filesystem.grep(rx, spec.file):
                    for asset in spec.assets:
                        if os.path.isfile(asset.src) and filesystem.grep(rx, asset.src):
                            break
                    else:
                        spec.mask = "@*{re.search(%r) is None} evaluated to @*g{True}" % regex
                        continue

    except Exception:
        state = "failed"
        raise
    else:
        state = "done"
    finally:
        end = "... %s (%.2fs.)\n" % (state, time.monotonic() - start)
        extra = {"end": end, "rewind": True}
        logger.log(logging.INFO, msg, extra=extra)


def propagate_masks(items: list["ResolvedSpec"]) -> None:
    changed: bool = True
    while changed:
        changed = False
        for item in items:
            if item.mask:
                continue
            if any(dep.mask for dep in item.dependencies):
                item.mask = "One or more dependencies masked"
                changed = True


def contains_any(elements: tuple[str, ...], test_elements: list[str]) -> bool:
    return any(element in test_elements for element in elements)
