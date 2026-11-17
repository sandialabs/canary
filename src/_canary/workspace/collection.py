# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Test collection and spec generation.

This module handles discovering test generators from filesystem paths
and generating JobSpec objects from those generators.
"""

from pathlib import Path
from typing import TYPE_CHECKING
from typing import Literal

from ..generation.collect import Collector
from ..generation.generate import Generator
from ..util import logging

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec
    from ..generation.generator import AbstractTestGenerator
    from ..persistence.database import WorkspaceDatabase

logger = logging.get_logger(__name__)


class SpecCollector:
    """Collects test generators and generates JobSpecs.

    This class handles the process of:
    1. Scanning filesystem paths for test generators
    2. Generating JobSpec objects from those generators
    3. Storing specs in the workspace database
    """

    def __init__(self, workspace_root: Path, db: "WorkspaceDatabase"):
        """Initialize spec collector.

        Args:
            workspace_root: Root path of the workspace.
            db: Workspace database for storing specs.
        """
        self.root = workspace_root
        self.db = db

    def collect(
        self,
        scanpaths: dict[str, list[str]],
        on_options: list[str] | None = None,
        parsing_policy: Literal["pedantic", "permissive"] = "pedantic",
    ) -> list["JobSpec"]:
        """Find test job generators in scan_paths and add them to this workspace.

        Args:
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
        resolved = self.generate_jobspecs(generators=generators, on_options=on_options)
        self.store_specs(resolved)
        return resolved

    def generate_jobspecs(
        self, generators: list["AbstractTestGenerator"], on_options: list[str] | None = None
    ) -> list["JobSpec"]:
        """Generate resolved test specs from generators.

        Args:
            generators: List of test generators.
            on_options: Used to filter tests by option.

        Returns:
            A list of resolved JobSpecs.
        """
        on_options = on_options or []
        generator = Generator(generators, workspace=self.root, on_options=on_options or [])
        resolved = generator.run()
        return resolved

    def store_specs(self, specs: list["JobSpec"]) -> None:
        """Cache the provided job specifications into the workspace database.

        Args:
            specs: The resolved job specifications to store.
        """
        pm = logger.progress_monitor("[bold]Caching[/] test specs")
        self.db.put_specs(specs)
        pm.done()
