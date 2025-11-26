# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import re
from typing import TYPE_CHECKING
from typing import Protocol

from .. import config
from .. import when
from . import filesystem
from . import logging

if TYPE_CHECKING:
    from ..testspec import ResolvedSpec

logger = logging.get_logger(__name__)


def apply_masks(
    specs: list["ResolvedSpec"],
    keyword_exprs: list[str] | None = None,
    parameter_expr: str | None = None,
    owners: list[str] | None = None,
    regex: str | None = None,
    ids: list[str] | None = None,
    prefixes: list[str] | None = None,
) -> None:
    """Filter test specs (mask test specs that don't meet a specific criteria)

    Args:
      keyword_exprs: Include those tests matching this keyword expressions
      parameter_expr: Include those tests matching this parameter expression
      ids: Include those tests matching these ids

    """
    rx: re.Pattern | None = None
    if regex is not None:
        logger.warning("Regular expression search can be slow for large test suites")
        rx = re.compile(regex)

    owners_set = set(owners or [])

    for spec in specs:
        if spec.mask:
            continue

        if ids is not None:
            if not any(spec.id.startswith(id) for id in ids):
                spec.mask = "test ID not in @*{%s}" % ",".join(ids)
            continue

        if prefixes is not None:
            if not any(str(spec.file).startswith(prefix) for prefix in prefixes):
                spec.mask = "test prefix does not match requested"
                continue

        try:
            check = config.pluginmanager.hook.canary_resource_pool_accommodates(case=spec)
        except Exception as e:
            if config.get("debug"):
                raise
            spec.mask = "@*{%s}(%r)" % (e.__class__.__name__, e.args[0])
            continue
        else:
            if not check:
                spec.mask = check.reason
                continue

        if owners_set and not owners_set.intersection(spec.owners or []):
            spec.mask = "not owned by @*{%r}" % spec.owners
            continue

        if keyword_exprs is not None:
            kwds = set(spec.keywords)
            kwds.update(spec.implicit_keywords)  # ty: ignore[invalid-argument-type]
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
                parameters=spec.parameters | spec.implicit_parameters,  # ty: ignore[unsupported-operator]
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


class Maskable(Protocol):
    mask: str
    dependencies: list["Maskable"]


def propagate_masks(items: list[Maskable]) -> None:
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
