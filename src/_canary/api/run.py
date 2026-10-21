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
from dataclasses import dataclass
from os import PathLike
from typing import Iterable
from typing import Literal
from typing import TypeAlias

from _canary import config
from _canary.app.run import RunOptions
from _canary.app.run import run as _app_run
from _canary.rerun import StrategyType
from _canary.view import ViewSettings

Pathish: TypeAlias = str | PathLike[str]
RunRequestKind: TypeAlias = Literal["scanpaths", "viewpaths", "specids", "tag"]


@dataclass(frozen=True, slots=True)
class RunRequest:
    """Application-level run request.

    This is the public API version of the structural request consumed by
    :func:`_canary.app.run.run`.

    Attributes:
        kind: Request kind.  Supported values are ``"scanpaths"``,
            ``"viewpaths"``, ``"specids"``, and ``"tag"``.
        value: Payload for the request.  ``scanpaths``, ``viewpaths``, and
            ``specids`` use lists of strings.  ``tag`` uses a single string.
    """

    kind: RunRequestKind
    value: list[str] | str

    @classmethod
    def scanpaths(cls, paths: Pathish | Iterable[Pathish]) -> "RunRequest":
        """Create a request that scans one or more filesystem paths."""

        values = _as_path_list(paths, name="paths")
        if not values:
            raise ValueError("paths must contain at least one path")
        return cls(kind="scanpaths", value=values)

    @classmethod
    def viewpaths(cls, prefixes: str | Iterable[str]) -> "RunRequest":
        """Create a request that reruns tests selected from view-path prefixes."""

        values = _as_str_list(prefixes, name="viewpaths")
        if not values:
            raise ValueError("viewpaths must contain at least one prefix")
        return cls(kind="viewpaths", value=values)

    @classmethod
    def specids(cls, ids: str | Iterable[str]) -> "RunRequest":
        """Create a request that reruns tests selected by spec IDs."""

        values = _as_str_list(ids, name="specids")
        if not values:
            raise ValueError("specids must contain at least one spec ID")
        return cls(kind="specids", value=values)

    @classmethod
    def tag(cls, name: str) -> "RunRequest":
        """Create a request that reruns tests from a named selection tag."""

        if not name:
            raise ValueError("tag name must be non-empty")
        return cls(kind="tag", value=name)


def run(
    paths: Pathish | Iterable[Pathish] | None = None,
    *,
    from_tag: str | None = None,
    specids: str | Iterable[str] | None = None,
    viewpaths: str | Iterable[str] | None = None,
    request: RunRequest | None = None,
    selection_tag: str | None = None,
    on_options: str | Iterable[str] | None = None,
    keyword_exprs: str | Iterable[str] | None = None,
    parameter_expr: str | None = None,
    owners: str | Iterable[str] | None = None,
    regex: str | None = None,
    only: StrategyType | None = None,
    view: ViewSettings | None = None,
    wipe_workspace: bool = False,
    work_tree: Pathish | None = None,
) -> int:
    """Run a Canary session and return its process-style exit code.

    Args:
        paths: Path or paths to scan for job definitions.  This is the common
            ``canary.run("examples/")`` case.
        from_tag: Existing Canary selection tag to run.  This corresponds to a
            request of kind ``"tag"``.
        specids: Spec ID or spec IDs to rerun.
        viewpaths: View-path prefixes to rerun.
        request: Explicit :class:`RunRequest`.  If provided, ``paths``,
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
        wipe_workspace: Remove an existing workspace before running.  This is
            only valid for scanpath requests.
        work_tree: Workspace root.  Defaults to the current working directory,
            matching the application layer.

    Returns:
        The session return code returned by :func:`_canary.app.run.run`.

    Examples:
        Run job definitions under ``examples/``::

            import canary

            rc = canary.api.run("examples/")

        Run only failed jobs from the default selection::

            import canary

            rc = canary.api.run(only="failed")

        Run a previous named selection::

            import canary

            rc = canary.api.run(from_tag="nightly")
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
        wipe_workspace=wipe_workspace,
        work_tree=os.fspath(work_tree) if work_tree is not None else None,
    )
    return run_request(req, options)


def run_request(request: RunRequest, options: RunOptions | None = None) -> int:
    """Run an already-built request.

    This is the lowest-level public entry point in the API module.  It exists so
    programs can construct a request explicitly while still using the stable API
    namespace.

    Args:
        request: A :class:`RunRequest` or compatible object with ``kind`` and
            ``value`` attributes.
        options: Optional :class:`RunOptions`.

    Returns:
        The session return code.
    """

    return _app_run(request, options)


def make_request(
    *,
    paths: Pathish | Iterable[Pathish] | None = None,
    from_tag: str | None = None,
    specids: str | Iterable[str] | None = None,
    viewpaths: str | Iterable[str] | None = None,
) -> RunRequest:
    """Build a :class:`RunRequest` from Python-friendly selector arguments.

    Exactly one of ``paths``, ``from_tag``, ``specids``, or ``viewpaths`` may be
    provided.  If none are provided, the configured default run tag is used.  That
    gives ``canary.api.run()`` the same high-level meaning as a no-argument run:
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
        return RunRequest.scanpaths(paths)

    if from_tag is not None:
        return RunRequest.tag(from_tag)

    if specids is not None:
        return RunRequest.specids(specids)

    if viewpaths is not None:
        return RunRequest.viewpaths(viewpaths)

    return RunRequest.tag(config.get("run:default_tag"))


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
    "RunRequest",
    "RunRequestKind",
    "Pathish",
    "make_request",
    "run",
    "run_request",
]
