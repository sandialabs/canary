# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Workspace location and discovery utilities.

This module provides pure utility functions for finding and resolving
Canary workspace locations without any stateful operations.
"""

from pathlib import Path

workspace_path = ".canary"
workspace_tag = "WORKSPACE.TAG"
workspace_breadcrumbs = (
    workspace_tag,
    "VERSION",
    "workspace.sqlite3",
    "config.yaml",
    "refs",
    "sessions",
    "cache",
    "logs",
    "reports",
)


class NotAWorkspaceError(Exception):
    """Raised when a directory is not recognized as a Canary workspace."""

    pass


class WorkspaceLocator:
    """Pure utility class for workspace discovery and resolution.

    All methods are static and have no side effects.
    """

    @staticmethod
    def exists_at(p: Path) -> bool:
        """Check if a path contains a tagged workspace.

        Args:
            p: Path to check for workspace.

        Returns:
            True if WORKSPACE.TAG exists at the path.
        """
        return (p / workspace_tag).exists()

    @staticmethod
    def workspace_at(path: str | Path) -> Path | None:
        """Return the workspace directory located exactly at path, or None.

        Unlike find_anchor, no upward search is performed. Path may be
        either the anchor directory (containing .canary) or the .canary
        directory itself. The directory must carry a WORKSPACE.TAG to be
        recognized, so arbitrary directories named .canary are never
        mistaken for workspaces. Intended for destructive operations, which
        must never act on an ancestor of the path the user named.

        Args:
            path: Path to check for workspace.

        Returns:
            The workspace directory if found at exact location, None otherwise.
        """
        p = Path(path).absolute()
        candidate = p if p.name == workspace_path else p / workspace_path
        if (
            candidate.is_dir()
            and not candidate.is_symlink()
            and WorkspaceLocator.exists_at(candidate)
        ):
            return candidate
        return None

    @staticmethod
    def removable_workspace_at(path: str | Path) -> Path | None:
        """Return the exact workspace occupant at path for explicit removal.

        This is broader than workspace_at: removal may detach a damaged
        .canary directory at the named path, while discovery/load stays
        strict and tag-based.

        Args:
            path: Path to check for removable workspace.

        Returns:
            The workspace directory if found and removable, None otherwise.
        """

        p = Path(path).absolute()
        candidate = p if p.name == workspace_path else p / workspace_path
        if not candidate.is_dir() or candidate.is_symlink():
            return None
        if WorkspaceLocator.exists_at(candidate):
            return candidate
        # Check for workspace breadcrumbs even without tag
        for name in workspace_breadcrumbs[1:]:
            if (candidate / name).exists():
                return candidate
        return None

    @staticmethod
    def find_anchor(start: str | Path | None = None) -> Path | None:
        """Search upward from start to find the directory containing the workspace.

        Args:
            start: The directory to start the search from. Defaults to the
                current working directory, resolved at call time.

        Returns:
            The anchor Path if found, otherwise None.
        """
        if start is None:
            start = Path.cwd()
        current_path = Path(start).absolute()
        if current_path.stem == workspace_path:
            return (
                current_path.parent
                if WorkspaceLocator.workspace_at(current_path) is not None
                else None
            )
        while True:
            if WorkspaceLocator.workspace_at(current_path) is not None:
                return current_path.parent if current_path.name == workspace_path else current_path
            if current_path.parent == current_path:
                break
            current_path = current_path.parent
        return None

    @staticmethod
    def find_workspace(start: str | Path | None = None) -> Path | None:
        """Locate the .canary workspace directory.

        Args:
            start: The directory to start the search from. Defaults to the
                current working directory, resolved at call time.

        Returns:
            The path to the workspace directory if found, otherwise None.
        """
        if anchor := WorkspaceLocator.find_anchor(start=start):
            return anchor / workspace_path
        return None

    @staticmethod
    def resolve_explicit_workspace_dir(path: str | Path) -> Path:
        """Resolve an explicit workspace reference to the workspace root directory.

        Accepts either:
        - the workspace directory itself (contains WORKSPACE.TAG), or
        - an anchor directory that contains a .canary child.

        Args:
            path: Path to workspace or anchor directory.

        Returns:
            The workspace root directory.

        Raises:
            NotAWorkspaceError: If neither form resolves to a valid workspace.
        """
        p = Path(path).absolute()
        if WorkspaceLocator.exists_at(p):
            return p
        candidate = p / workspace_path
        if WorkspaceLocator.exists_at(candidate):
            return candidate
        raise NotAWorkspaceError(f"not a Canary workspace: {p}")
