# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Generator

from ... import config
from ...util import masking
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...testspec import ResolvedSpec


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
    masking.apply_masks(
        specs=specs,
        keyword_exprs=keyword_exprs,
        parameter_expr=parameter_expr,
        owners=owners,
        regex=regex,
        ids=ids,
    )
    yield
    masking.propagate_masks(specs)
