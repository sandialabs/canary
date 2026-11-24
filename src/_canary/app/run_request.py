# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Public programming interface for running Canary sessions.

This module is the API analogue of the ``canary run`` subcommand.  It accepts
ordinary Python values, builds the application-level run request and
``RunOptions``, and delegates execution to :mod:`_canary.app.run`.

The command-line layer is responsible for parsing argv.  This layer is
responsible for providing a stable, typed, Python-facing interface.
"""

import os
from os import PathLike
from typing import Iterable
from typing import Literal
from typing import TypeAlias

from _canary import config
from _canary.app.run import RunOptions
from _canary.app.run import run as _app_run
from _canary.rerun import StrategyType
from _canary.scanpaths import merge_scanpaths
from _canary.scanpaths import scanpath_from_item
from _canary.view import ViewSettings

from .pathspec import RequestNode
from .pathspec import ScanPathsRequest
from .pathspec import SpecIdsRequest
from .pathspec import TagRequest
from .pathspec import ViewPathsRequest

Pathish: TypeAlias = str | PathLike[str]


def scanpaths_request(paths: Pathish | Iterable[Pathish]) -> ScanPathsRequest:
    """A request that scans one or more filesystem paths (resolved now, as ``canary run`` does)."""

    values = _as_path_list(paths, name="paths")
    if not values:
        raise ValueError("paths must contain at least one path")
    return ScanPathsRequest(value=_scanpaths(values))


def viewpaths_request(prefixes: str | Iterable[str]) -> ViewPathsRequest:
    """A request that reruns tests selected from view-path prefixes."""

    values = _as_str_list(prefixes, name="viewpaths")
    if not values:
        raise ValueError("viewpaths must contain at least one prefix")
    return ViewPathsRequest(value=values)


def specids_request(ids: str | Iterable[str]) -> SpecIdsRequest:
    """A request that reruns tests selected by spec IDs."""

    values = _as_str_list(ids, name="specids")
    if not values:
        raise ValueError("specids must contain at least one spec ID")
    return SpecIdsRequest(value=values)


def tag_request(name: str) -> TagRequest:
    """A request that reruns tests from a named selection tag."""

    if not name:
        raise ValueError("tag name must be non-empty")
    return TagRequest(value=name)


def run(
    paths: Pathish | Iterable[Pathish] | None = None,
    *,
    from_tag: str | None = None,
    specids: str | Iterable[str] | None = None,
    viewpaths: str | Iterable[str] | None = None,
    request: RequestNode | None = None,
    selection_tag: str | None = None,
    on_options: str | Iterable[str] | None = None,
    keyword_exprs: str | Iterable[str] | None = None,
    parameter_expr: str | None = None,
    owners: str | Iterable[str] | None = None,
    regex: str | None = None,
    only: StrategyType | None = None,
    view: ViewSettings | None = None,
    parsing_policy: Literal["pedantic", "permissive"] = "pedantic",
    wipe_workspace: bool = False,
    work_tree: Pathish | None = None,
) -> int:
    """Run a Canary session and return its process-style exit code.

    Args:
        paths: Path or paths to scan for job definitions.  This is the common
            ``run("examples/")`` case.
        from_tag: Existing Canary selection tag to run.  This corresponds to a
            request of kind ``"tag"``.
        specids: Spec ID or spec IDs to rerun.
        viewpaths: View-path prefixes to rerun.
        request: An explicit request (:func:`make_request`, :func:`scanpaths_request`, ...).  If provided, ``paths``,
            ``from_tag``, ``specids``, and ``viewpaths`` must be omitted.
        selection_tag: Name to assign to a newly-created scanpath selection.
            This maps to :attr:`RunOptions.tag`.  It is intentionally named
            differently from ``from_tag`` to avoid ambiguity.
        on_options: Build/generation options, equivalent to repeated ``-o``.
        keyword_exprs: Keyword filter expression or expressions.
        parameter_expr: Parameter filter expression.
        owners: Owner filter or filters.
        regex: File-content regular-expression filter.
        only: Rerun strategy.  Supported built-ins are defined by
            :mod:`_canary.rerun`.
        view: Optional result-view settings.
        parsing_policy: How collection handles parse/import failures in test
            files. ``pedantic`` stops on failures; ``permissive`` keeps them as
            masked specs.
        wipe_workspace: Remove an existing workspace before running.  This is
            only valid for scanpath requests.
        work_tree: Workspace root.  Defaults to the current working directory,
            matching the application layer.

    Returns:
        The session return code returned by :func:`_canary.app.run.run`.

    Examples:
        Run job definitions under ``examples/``::

            from _canary.app.run_request import run

            rc = run("examples/")

        Run only failed jobs from the default selection::

            rc = run(only="failed")

        Run a previous named selection::

            rc = run(from_tag="nightly")
    """

    req = request or make_request(
        paths=paths, from_tag=from_tag, specids=specids, viewpaths=viewpaths
    )

    options = RunOptions(
        tag=selection_tag,
        on_options=_as_optional_str_list(on_options, name="on_options"),
        keyword_exprs=_as_optional_str_list(keyword_exprs, name="keyword_exprs"),
        parameter_expr=parameter_expr,
        owners=_as_optional_str_list(owners, name="owners"),
        regex=regex,
        only=only,
        view=view,
        parsing_policy=parsing_policy,
        wipe_workspace=wipe_workspace,
        work_tree=os.fspath(work_tree) if work_tree is not None else None,
    )
    return run_request(req, options)


def run_request(request: RequestNode, options: RunOptions | None = None) -> int:
    """Run an already-built request (see :func:`make_request`, :func:`scanpaths`, ...).

    Returns:
        The session return code.
    """

    return _app_run(request, options)


def _scanpaths(paths: Iterable[str]) -> dict[str, list[str]]:
    """Resolve path arguments into ``{root: [paths]}`` exactly as ``canary run PATH`` does.

    Relative paths are resolved against the current directory.
    """
    scanpaths: dict[str, list[str]] = {}
    for item in paths:
        found = scanpath_from_item(item)
        if found is None:
            raise ValueError(f"{item}: no such file or directory")
        merge_scanpaths(scanpaths, found)
    return scanpaths


def make_request(
    *,
    paths: Pathish | Iterable[Pathish] | None = None,
    from_tag: str | None = None,
    specids: str | Iterable[str] | None = None,
    viewpaths: str | Iterable[str] | None = None,
) -> RequestNode:
    """Build a run request from Python-friendly selector arguments.

    Exactly one of ``paths``, ``from_tag``, ``specids``, or ``viewpaths`` may be
    provided.  If none are provided, the configured default run tag is used.  That
    gives ``run()`` the same high-level meaning as a no-argument run:
    run the default saved selection rather than implicitly scanning ``.``.
    """

    provided = [
        name
        for name, value in (
            ("paths", paths),
            ("from_tag", from_tag),
            ("specids", specids),
            ("viewpaths", viewpaths),
        )
        if value is not None
    ]

    if len(provided) > 1:
        joined = ", ".join(provided)
        raise ValueError(f"run request is ambiguous; provide only one of: {joined}")

    if paths is not None:
        return scanpaths_request(paths)

    if from_tag is not None:
        return tag_request(from_tag)

    if specids is not None:
        return specids_request(specids)

    if viewpaths is not None:
        return viewpaths_request(viewpaths)

    return tag_request(config.get("run:default_tag"))


def _as_optional_str_list(value: str | Iterable[str] | None, *, name: str) -> list[str] | None:
    if value is None:
        return None
    return _as_str_list(value, name=name)


def _as_path_list(value: Pathish | Iterable[Pathish], *, name: str) -> list[str]:
    if isinstance(value, (str, os.PathLike)):
        return [os.fspath(value)]
    try:
        return [os.fspath(item) for item in value]
    except TypeError as exc:
        raise TypeError(f"{name} must be a path or iterable of paths") from exc


def _as_str_list(value: str | Iterable[str], *, name: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    try:
        return [str(item) for item in value]
    except TypeError as exc:
        raise TypeError(f"{name} must be a string or iterable of strings") from exc


__all__ = [
    "RunOptions",
    "Pathish",
    "make_request",
    "run",
    "run_request",
    "scanpaths_request",
    "specids_request",
    "tag_request",
    "viewpaths_request",
]
