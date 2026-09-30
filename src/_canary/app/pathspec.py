# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Run-request model and ``canary run`` path-specification classification.

A *run request* is the typed description of what ``canary run`` (and future
interfaces) should run: a set of scan paths, a set of view paths, a set of spec
ids, or a selection tag.  The request types and the builder that assembles them
live here, in the application layer, because they are the contract
:func:`_canary.app.run.run` consumes -- not a CLI detail.

``canary run`` also accepts free-form "pathspec" items that must be classified
into one of those request kinds.  Deciding whether an item is a directory, a
file, a view path, a tag, or a spec id requires the current workspace, so the
classification is an application operation (:func:`classify_pathspec`) rather
than something an argparse action should do.  The CLI tokenises the raw
arguments (splitting the ``--`` script-argument separator) and calls this
module; resolution errors are returned as data so the CLI can surface them as a
usage error.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Literal
from typing import Optional

from ..generation.collect import vc_prefixes
from ..session.workspace import NotAWorkspaceError
from ..session.workspace import Workspace

ScanPathPayload = dict[str, list[str]]  # root -> [files]; empty list means "scan all"
ViewPathPayload = list[str]  # e.g. ["rel/path/%", ...]
SpecIdPayload = list[str]  # full spec ids


@dataclass(frozen=True, slots=True)
class RequestNode:
    """Abstract base for a typed run-request carrying a payload value.

    Attributes:
        kind: One of ``"scanpaths"``, ``"viewpaths"``, ``"specids"``, or ``"tag"``.
        value: The request payload, whose type depends on ``kind``.
    """

    kind: Literal["scanpaths", "viewpaths", "specids", "tag"]
    value: Any

    def __serialize__(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": self.value}

    @classmethod
    def __deserialize__(cls, d: dict) -> "RequestNode":
        return cls(**d)


@dataclass(frozen=True, slots=True)
class ScanPathsRequest(RequestNode):
    """Run request that scans directories/files for test generators."""

    kind: Literal["scanpaths"] = "scanpaths"
    value: ScanPathPayload = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ViewPathsRequest(RequestNode):
    """Run request that re-runs tests from a previous session view."""

    kind: Literal["viewpaths"] = "viewpaths"
    value: ViewPathPayload = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SpecIdsRequest(RequestNode):
    """Run request that re-runs specific tests by spec ID."""

    kind: Literal["specids"] = "specids"
    value: SpecIdPayload = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TagRequest(RequestNode):
    """Run request that re-runs tests belonging to a named tag."""

    kind: Literal["tag"] = "tag"
    value: str = ""


@dataclass
class RequestBuilder:
    """Mutable accumulator that collects pathspec items and produces a :class:`RequestNode`.

    A single request *kind* is inferred across all items; attempting to mix
    kinds records a conflict in the caller-supplied error list rather than
    raising, so every problem in a pathspec can be reported at once.
    """

    kind: str | None = None
    scanpaths: ScanPathPayload = field(default_factory=dict)
    viewpaths: ViewPathPayload = field(default_factory=list)
    specids: SpecIdPayload = field(default_factory=list)
    tag: Optional[str] = None
    errors: list[str] = field(default_factory=list)

    def __serialize__(self) -> dict[str, Any]:
        return vars(self)

    @classmethod
    def __deserialize__(cls, d: dict) -> "RequestBuilder":
        return cls(**d)

    def require_kind(self, k: str, what: str) -> None:
        """Fix the request kind to *k*, recording a conflict error if it differs."""
        if self.kind is None:
            self.kind = k
        elif self.kind != k:
            self.errors.append(f"Cannot mix {self.kind} with {what}")

    def finalize(self) -> RequestNode | None:
        """Convert the accumulated state into an immutable :class:`RequestNode`, or ``None``."""
        if self.kind is None:
            return None
        if self.kind == "tag":
            return TagRequest(value=self.tag or "")
        if self.kind == "scanpaths":
            return ScanPathsRequest(value=self.scanpaths)
        if self.kind == "viewpaths":
            return ViewPathsRequest(value=self.viewpaths)
        if self.kind == "specids":
            return SpecIdsRequest(value=self.specids)
        raise RuntimeError(f"Unknown request kind: {self.kind!r}")


def classify_pathspec(items: list[str], *, builder: RequestBuilder | None = None) -> RequestBuilder:
    """Classify *items* into a single run-request kind against the current workspace.

    Opens the nearest workspace if one exists (its absence is not an error: new
    scan-path runs create one later).  Tags, view paths, and spec ids are only
    recognised when a workspace is available.  Classification problems are
    appended to the returned builder's ``errors`` rather than raised.

    Args:
        items: Already-tokenised pathspec items (the ``--`` script-argument
            separator must be stripped by the caller).
        builder: An existing builder to extend (so a request can be assembled
            from more than one source, e.g. a ``-f`` file plus positional
            items); a fresh one is created when omitted.

    Returns:
        The builder, carrying the inferred kind, payloads, and any errors.
    """
    builder = builder if builder is not None else RequestBuilder()
    workspace = _load_workspace_or_none()
    possible_specs: list[str] = []

    for item in items:
        _classify_item(item, workspace, builder, possible_specs)

    _classify_possible_specs(possible_specs, workspace, builder)
    return builder


def _load_workspace_or_none() -> Workspace | None:
    try:
        return Workspace.load()
    except NotAWorkspaceError:
        return None


def _classify_item(
    item: str, workspace: Workspace | None, builder: RequestBuilder, possible_specs: list[str]
) -> None:
    """Classify a single *item*, deferring unresolved ids to *possible_specs*.

    The branch order is significant: lock files are rejected first; tags and
    view paths (workspace-relative meanings) take precedence over on-disk paths;
    the version-control and ``root:name`` forms come last before an item is
    deferred as a possible spec id.
    """
    abspath = os.path.abspath(item)

    if os.path.isfile(item) and item.endswith("testcases.lock"):
        builder.errors.append(f"{item}: lock file scanning not implemented")
        return

    if workspace and workspace.is_tag(item):
        builder.require_kind("tag", f"tag {item}")
        builder.tag = item
        return

    if workspace and (rel_path := workspace.relative_to_view(abspath)):
        builder.require_kind("viewpaths", f"viewpaths {abspath}")
        p = rel_path if os.path.isfile(abspath) else rel_path.rstrip("/") + "/%"
        builder.viewpaths.append(p)
        return

    if os.path.isdir(abspath):
        builder.require_kind("scanpaths", f"scanpaths {abspath}")
        builder.scanpaths.setdefault(abspath, [])
        return

    if os.path.isfile(abspath):
        builder.require_kind("scanpaths", f"scanpaths {abspath}")
        root, name = os.path.split(abspath)
        builder.scanpaths.setdefault(root, []).append(name)
        return

    if item.startswith(vc_prefixes):
        path_part = item.partition("@")[2]
        if not os.path.isdir(path_part):
            builder.errors.append(f"{path_part}: no such directory")
            return
        builder.require_kind("scanpaths", f"scanpaths {abspath}")
        builder.scanpaths.setdefault(item, [])
        return

    if os.pathsep in item and os.path.exists(item.replace(os.pathsep, os.path.sep)):
        builder.require_kind("scanpaths", f"scanpaths {abspath}")
        root, name = item.split(os.pathsep, 1)
        builder.scanpaths.setdefault(os.path.abspath(root), []).append(
            name.replace(os.pathsep, os.path.sep)
        )
        return

    possible_specs.append(item)


def _classify_possible_specs(
    possible_specs: list[str], workspace: Workspace | None, builder: RequestBuilder
) -> None:
    """Resolve deferred items as spec ids, recording invalid ones as errors."""
    if not possible_specs:
        return
    if workspace is None:
        builder.errors.append("Spec IDs require an active workspace")
        return
    builder.require_kind("specids", "specids")
    found_ids = workspace.find_specids(possible_specs)
    for item, found in zip(possible_specs, found_ids):
        if found is None:
            builder.errors.append(f"{item}: not a valid test identifier")
        else:
            builder.specids.append(found)
