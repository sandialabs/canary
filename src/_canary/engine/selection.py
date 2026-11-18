# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Test selection and filtering.

This module handles filtering JobSpecs using selection rules and managing
tagged selections in the database.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from .. import select
from ..core import rules
from ..scanpaths import case_selectors
from ..util import logging
from ..util.names import unique_random_name

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec
    from ..persistence.database import WorkspaceDatabase

logger = logging.get_logger(__name__)


class SpecSelector:
    """Filters JobSpecs and manages selection tags.

    This class handles:
    1. Filtering specs using selection rules (keywords, parameters, owners, etc.)
    2. Creating and managing tagged selections in the database
    3. Tag validation and queries
    """

    def __init__(self, workspace_root: Path, db: "WorkspaceDatabase"):
        """Initialize spec selector.

        Args:
            workspace_root: Root path of the workspace.
            db: Workspace database for storing/loading specs and selections.
        """
        self.root = workspace_root
        self.db = db

    def select(
        self,
        tag: str,
        prefixes: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> list["JobSpec"]:
        """Select specs from database with filters, save as tag.

        Args:
            tag: The name of the selection tag to create.
            prefixes: Filter by path prefixes.
            keyword_exprs: Filter by keywords.
            parameter_expr: Filter by parameter expressions.
            owners: Filter by owners.
            regex: Filter by regular expression.

        Returns:
            The list of selected JobSpecs.
        """
        resolved = self.db.load_specs()
        specs = self.select_from_specs(
            resolved,
            prefixes=prefixes,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
        )
        self.db.put_selection(
            tag,
            specs,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
        )
        return specs

    def select_from_specs(
        self,
        resolved: list["JobSpec"],
        prefixes: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
        extra_rules: list["rules.Rule"] | None = None,
    ) -> list["JobSpec"]:
        """Filter specs using provided rules.

        Args:
            resolved: The list of specs to filter.
            prefixes: Filter by path prefixes.
            keyword_exprs: Filter by keywords.
            parameter_expr: Filter by parameter expressions.
            owners: Filter by owners.
            regex: Filter by regular expression.
            extra_rules: Additional selection rules (e.g. a file::case rule).

        Returns:
            The filtered list of JobSpecs.
        """
        selector = select.Selector(resolved, self.root)
        for rule in _filter_rules(keyword_exprs, parameter_expr, owners, regex):
            selector.add_rule(rule)
        if prefixes:
            selector.add_rule(rules.PrefixRule(prefixes=prefixes))
        for rule in extra_rules or ():
            selector.add_rule(rule)
        specs = selector.run()
        return specs

    def select_from_tag(
        self,
        tag: str,
        source_tag: str,
        prefixes: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> list["JobSpec"]:
        """Create selection *tag* by filtering the specs already in *source_tag*.

        Unlike :meth:`select`, which draws from every spec in the workspace, this
        starts from the specs stored under *source_tag* and applies the given
        filters before saving the result as *tag*.

        Args:
            tag: The name of the selection tag to create.
            source_tag: The existing tag whose specs are filtered.
            prefixes: Filter by path prefixes.
            keyword_exprs: Filter by keywords.
            parameter_expr: Filter by parameter expressions.
            owners: Filter by owners.
            regex: Filter by regular expression.

        Returns:
            The list of selected JobSpecs.
        """
        resolved = self.db.load_specs_by_tagname(source_tag)
        specs = self.select_from_specs(
            resolved,
            prefixes=prefixes,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
        )
        self.db.put_selection(
            tag,
            specs,
            prefixes=prefixes,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
        )
        return specs

    def create_selection(
        self,
        tag: str | None,
        resolved: list["JobSpec"],
        scanpaths: dict[str, list[str]],
        on_options: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> list["JobSpec"]:
        """Filter specs collected from *scanpaths* and save them as a tagged selection.

        Args:
            tag: Tag name (randomly generated if None).
            resolved: Specs collected from *scanpaths*.
            scanpaths: The scan paths (``file::case`` selectors become a case rule).
            on_options: Options the specs were collected with (recorded in metadata).
            keyword_exprs: Filter by keywords.
            parameter_expr: Filter by parameters.
            owners: Filter by owners.
            regex: Filter by regex.

        Returns:
            The created selection of JobSpecs.
        """
        case_rule: rules.CaseRule | None = None
        if cases := case_selectors(scanpaths):
            case_rule = rules.CaseRule.from_specs(resolved, cases)
        specs = self.select_from_specs(
            resolved,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
            extra_rules=[case_rule] if case_rule else None,
        )
        tag = tag or unique_random_name(self.db.tags)
        self.db.put_selection(
            tag,
            specs,
            scanpaths=scanpaths,
            on_options=on_options,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
        )
        logger.info(f"[bold]Created[/] selection '[bold]{tag}[/]'")
        return specs

    def apply_selection_rules(
        self,
        specs: list["JobSpec"],
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Filter specs in-place using rules.

        Args:
            specs: The list of specs to filter.
            keyword_exprs: Filter by keywords.
            parameter_expr: Filter by parameters.
            owners: Filter by owners.
            regex: Filter by regex.
            ids: Filter by specific IDs.
        """
        selector = select.Selector(specs, self.root)
        for rule in _filter_rules(keyword_exprs, parameter_expr, owners, regex):
            selector.add_rule(rule)
        if ids:
            selector.add_rule(rules.IDsRule(ids))
        if selector.rules:
            selector.run()


def _filter_rules(
    keyword_exprs: list[str] | None,
    parameter_expr: str | None,
    owners: list[str] | None,
    regex: str | None,
) -> list["rules.Rule"]:
    """Selection rules for the common keyword/parameter/owner/regex filters."""
    found: list[rules.Rule] = []
    if keyword_exprs:
        found.append(rules.KeywordRule(keyword_exprs))
    if parameter_expr:
        found.append(rules.ParameterRule(parameter_expr))
    if owners:
        found.append(rules.OwnersRule(owners))
    if regex:
        found.append(rules.RegexRule(regex))
    return found
