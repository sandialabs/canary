# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Generator

from ... import config
from ...util import logging
from ...util import masking
from ...util.string import pluralize
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...testspec import ResolvedSpec


logger = logging.get_logger(__name__)


@hookimpl(wrapper=True)
def canary_select(
    specs: list["ResolvedSpec"],
    keyword_exprs: list[str] | None,
    parameter_expr: list[str] | None,
    owners: list[str] | None,
    regex: str | None,
    prefixes: list[str] | None,
    ids: list[str] | None,
) -> Generator[None, None, None]:
    """Filter test cases (mask test cases that don't meet a specific criteria)

    Args:
      keyword_exprs: Include those tests matching this keyword expressions
      parameter_expr: Include those tests matching this parameter expression
      start: The starting directory the python session was invoked in
      case_specs: Include those tests matching these specs

    """
    yield
    masking.propagate_masks(specs)  # ty: ignore[invalid-argument-type]
    return


@hookimpl(tryfirst=True, specname="canary_select")
def mask_testspecs(
    specs: list["ResolvedSpec"],
    keyword_exprs: list[str] | None,
    parameter_expr: str | None,
    owners: list[str] | None,
    regex: str | None,
    prefixes: list[str] | None,
    ids: list[str] | None,
) -> None:
    masking.apply_masks(
        specs,
        prefixes=prefixes,
        keyword_exprs=keyword_exprs,
        parameter_expr=parameter_expr,
        regex=regex,
        owners=owners,
        ids=ids,
    )


@hookimpl
def canary_select_report(specs: list["ResolvedSpec"]) -> None:
    excluded: list["ResolvedSpec"] = []
    for spec in specs:
        if spec.mask:
            excluded.append(spec)
    n = len(specs) - len(excluded)
    logger.info("@*{Selected} %d test %s" % (n, pluralize("spec", n)))
    if excluded:
        n = len(excluded)
        logger.info("@*{Excluded} %d test specs for the following reasons:" % n)
        reasons: dict[str | None, list["ResolvedSpec"]] = {}
        for spec in excluded:
            if spec.mask:
                reasons.setdefault(spec.mask, []).append(spec)
        keys = sorted(reasons, key=lambda x: len(reasons[x]))
        for key in reversed(keys):
            reason = key if key is None else key.lstrip()
            n = len(reasons[key])
            logger.log(logging.EMIT, f"• {reason} ({n} excluded)", extra={"prefix": ""})
            if config.getoption("show_excluded_tests"):
                for spec in reasons[key]:
                    logger.log(logging.EMIT, f"◦ {spec.display_name}", extra={"prefix": ""})
