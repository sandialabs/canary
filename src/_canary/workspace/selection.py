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
from typing import Any
from typing import Literal

from .. import select
from ..core import rules
from ..scanpaths import case_selectors
from ..util import logging
from ..util.names import unique_random_name

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec
    from ..persistence.database import WorkspaceDatabase
    from .collection import SpecCollector

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
        if keyword_exprs:
            selector.add_rule(rules.KeywordRule(keyword_exprs))
        if parameter_expr:
            selector.add_rule(rules.ParameterRule(parameter_expr))
        if owners:
            selector.add_rule(rules.OwnersRule(owners))
        if regex:
            selector.add_rule(rules.RegexRule(regex))
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
        """Create selection by filtering specs in source_tag.

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
        scanpaths: dict[str, list[str]],
        collector: "SpecCollector",
        on_options: list[str] | None = None,
        parsing_policy: Literal["pedantic", "permissive"] = "pedantic",
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> list["JobSpec"]:
        """Collect generators, filter, and create tagged selection.

        Args:
            tag: Tag name (randomly generated if None).
            scanpaths: Paths to scan for generators.
            collector: SpecCollector instance for collecting specs.
            on_options: Options to filter tests by.
            parsing_policy: How to handle parsing errors.
            keyword_exprs: Filter by keywords.
            parameter_expr: Filter by parameters.
            owners: Filter by owners.
            regex: Filter by regex.

        Returns:
            The created selection of JobSpecs.
        """
        resolved = collector.collect(
            scanpaths, on_options=on_options, parsing_policy=parsing_policy
        )
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
        if keyword_exprs:
            selector.add_rule(rules.KeywordRule(keyword_exprs))
        if parameter_expr:
            selector.add_rule(rules.ParameterRule(parameter_expr))
        if owners:
            selector.add_rule(rules.OwnersRule(owners))
        if regex:
            selector.add_rule(rules.RegexRule(regex))
        if ids:
            selector.add_rule(rules.IDsRule(ids))
        if selector.rules:
            selector.run()

    def remove_tag(self, tag: str) -> bool:
        """Delete selection tag from database.

        Args:
            tag: The tag name to remove.

        Returns:
            True if the tag was removed, False if it didn't exist.
        """
        if not self.db.is_selection(tag):
            logger.error(f"{tag!r} is not a tag")
            return False
        self.db.delete_selection(tag)
        return True

    def is_tag(self, tag: str) -> bool:
        """Check if string is valid selection tag.

        Args:
            tag: The string to check.

        Returns:
            True if it is a selection tag, False otherwise.
        """
        return self.db.is_selection(tag)

    def get_selection(self, tag: str | None) -> list["JobSpec"]:
        """Retrieve specs associated with tag.

        Args:
            tag: The tag name, or None/:all: for all specs.

        Returns:
            A list of JobSpecs.
        """
        if tag is None or tag == ":all:":
            return self.db.load_specs()
        return self.db.load_specs_by_tagname(tag)

    def tag_info(self, tag: str) -> dict[str, Any]:
        """Return metadata and specs for selection tag.

        Args:
            tag: The selection tag to describe.

        Returns:
            Dict with tag, created_on, metadata, and specs.
        """
        specs = [spec for spec in self.db.load_specs_by_tagname(tag) if not spec.mask]
        metadata = self.db.get_selection_metadata(tag)
        created_on = metadata.pop("created_on", None)
        return {"tag": tag, "created_on": created_on, "metadata": metadata, "specs": specs}
