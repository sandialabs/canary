# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Test collection: scan paths -> generators -> resolved JobSpecs, cached in the database."""

from pathlib import Path
from typing import TYPE_CHECKING
from typing import Literal

from ..generation.collect import Collector
from ..generation.generate import Generator
from ..util import logging

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec
    from ..persistence.database import WorkspaceDatabase

logger = logging.get_logger(__name__)


def collect_specs(
    root: Path,
    db: "WorkspaceDatabase",
    scanpaths: dict[str, list[str]],
    on_options: list[str] | None = None,
    parsing_policy: Literal["pedantic", "permissive"] = "pedantic",
) -> list["JobSpec"]:
    """Find test generators in *scanpaths*, resolve their specs, and store them in *db*.

    Args:
        root: Workspace root (generators resolve paths against it).
        db: Workspace database the specs are cached in.
        scanpaths: Dictionary of root paths to scan.
        on_options: Options used to filter tests by option.
        parsing_policy: How to handle parsing errors.

    Returns:
        A list of resolved JobSpecs.
    """
    collector = Collector()
    collector.add_scanpaths(scanpaths)
    collector.parsing_policy = parsing_policy
    generators = collector.run()
    resolved = Generator(generators, workspace=root, on_options=on_options or []).run()
    pm = logger.progress_monitor("[bold]Caching[/] test specs")
    db.put_specs(resolved)
    pm.done()
    return resolved
