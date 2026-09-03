# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Rerun strategy registry and spec-set computation.

A *rerun strategy* is a named function that queries the workspace database and
returns the set of spec IDs that should be re-executed.  Strategies are
registered via the :func:`rerun_strategy` decorator and are listed in the
``STRATEGIES`` dict.

The :func:`get_specs` entry point resolves a strategy name to the matching
function, computes the root spec set, and then expands it to include all
downstream dependents (and their upstream prerequisites) via
:func:`compute_rerun_closure`.

Built-in strategies:

- ``all`` — every spec in the workspace (or tag).
- ``changed`` — specs whose source file is newer than their last result.
- ``failed`` — specs whose last result category is FAIL, plus BLOCKED specs.
- ``not_pass`` — specs with no result or a non-PASS result.
- ``not_run`` — specs that have never produced a result.
"""

from typing import TYPE_CHECKING
from typing import Callable
from typing import Iterable
from typing import Literal

from .database import WorkspaceDatabase
from .jobspec import Mask

if TYPE_CHECKING:
    from .jobspec import JobSpec


StrategyType = Literal["changed", "all"]
STRATEGIES: dict[str, Callable[..., set[str]]] = {}


def compute_rerun_closure(db: WorkspaceDatabase, roots: Iterable[str]) -> list["JobSpec"]:
    """Expand a set of root spec IDs into a fully closed rerun spec list.

    The closure includes:

    - All specs in *roots* (to be run).
    - All downstream dependents of *roots* (transitively; also run).
    - All upstream prerequisites of the above (loaded but **masked** — they
      are needed for dependency resolution but will not be re-executed unless
      they are also in *roots*).

    Args:
        db: The workspace database to query.
        roots: Spec IDs that are the seeds of the rerun.

    Returns:
        A list of :class:`~_canary.jobspec.JobSpec` objects.  Upstream specs
        that are not in the run set have ``spec.mask`` set to a skip mask.
    """
    roots = set(roots)
    upstream, downstream = db.get_updownstream_ids(seeds=list(roots))
    runspecs = roots | downstream
    getspecs = runspecs | upstream
    resolved = db.load_specs(ids=list(getspecs))
    for spec in resolved:
        if spec.id not in runspecs:
            spec.mask = Mask(True, reason="Skip upstream specs")
    return resolved


def get_specs_from_view(db: WorkspaceDatabase, *, prefixes: list[str]) -> list["JobSpec"]:
    """Return the rerun closure for specs identified by ID prefixes in the view.

    Args:
        db: The workspace database to query.
        prefixes: Short spec ID prefixes (e.g. 7-char hex strings) to look up.

    Returns:
        Expanded rerun spec list; see :func:`compute_rerun_closure`.
    """
    roots = db.select_from_view(prefixes=prefixes)
    return compute_rerun_closure(db, roots=roots)


def get_specs(
    db: WorkspaceDatabase, *, strategy: StrategyType = "all", tag: str | None = None
) -> list["JobSpec"]:
    """Compute the full rerun spec set using a named strategy.

    Args:
        db: The workspace database to query.
        strategy: Name of a registered rerun strategy (see :func:`rerun_strategy`).
        tag: Optional workspace tag to restrict the query to a named selection.

    Returns:
        Expanded rerun spec list; empty list if the strategy selects no roots.

    Raises:
        ValueError: If *strategy* is not a registered strategy name.
    """
    try:
        selector = STRATEGIES[strategy]
    except KeyError:
        raise ValueError(f"Unknown rerun strategy: {strategy!r}")
    roots = selector(db, tag=tag)
    if not roots:
        return []
    return compute_rerun_closure(db, roots=roots)


def rerun_strategy(fn: Callable[..., set[str]]) -> Callable[..., set[str]]:
    """Decorator that registers a function as a named rerun strategy.

    The function name becomes the strategy key in ``STRATEGIES``.  Duplicate
    names raise ``RuntimeError``.

    Args:
        fn: A callable ``(db, *, tag) -> set[str]`` that returns spec IDs.

    Returns:
        The original function, unchanged.
    """
    name = fn.__name__
    if name in STRATEGIES:
        raise RuntimeError(f"Duplicate rerun strategy: {name}")
    STRATEGIES[name] = fn
    return fn


@rerun_strategy
def changed(db: WorkspaceDatabase, *, tag: str | None = None) -> set[str]:
    """Specs whose source file mtime is newer than the timestamp of their latest result."""
    pspecs = db.get_partial_specs(tag=tag)
    ids: set[str] = set()
    for pspec in pspecs:
        mtime = pspec.file.stat().st_mtime
        if pspec.started_at > 0 and mtime > pspec.started_at:
            ids.add(pspec.id)
    return ids


@rerun_strategy
def not_pass(db: WorkspaceDatabase, *, tag: str | None = None) -> set[str]:
    """Specs with no result or a non-PASS result category."""
    ids: set[str] = set()
    pspecs = db.get_partial_specs(tag=tag)
    for pspec in pspecs:
        if pspec.result_category != "PASS":
            ids.add(pspec.id)
    return ids


@rerun_strategy
def failed(db: WorkspaceDatabase, *, tag: str | None = None) -> set[str]:
    """Specs whose latest result category is FAIL, plus specs that are BLOCKED."""
    ids: set[str] = set()
    pspecs = db.get_partial_specs(tag=tag)
    for pspec in pspecs:
        if pspec.result_category == "FAIL":
            ids.add(pspec.id)
        elif pspec.result_outcome == "BLOCKED":
            ids.add(pspec.id)
    return ids


@rerun_strategy
def not_run(db: WorkspaceDatabase, *, tag: str | None = None) -> set[str]:
    """Specs that have never produced a result (result category is ``None`` or ``'NONE'``)."""
    ids: set[str] = set()
    pspecs = db.get_partial_specs(tag=tag)
    for pspec in pspecs:
        if pspec.result_category in (None, "NONE"):
            ids.add(pspec.id)
    return ids


@rerun_strategy
def all(db: WorkspaceDatabase, *, tag: str | None = None) -> set[str]:
    """All specs in the workspace (or tag) — re-run everything."""
    pspecs = db.get_partial_specs(tag=tag)
    return {c.id for c in pspecs}


def setup_parser(parser) -> None:
    """Add the ``--only`` argument for choosing a rerun strategy to *parser*."""
    parser.add_argument(
        "--only",
        dest="only",
        choices=sorted(STRATEGIES.keys()),
        default="not_pass",
        help="Which tests to run after selection\n\n"
        "  all      - run all selected tests, even if already passing\n\n"
        "  failed   - run only previously failing tests\n\n"
        "  not_run  - run tests that have never been executed\n\n"
        "  changed  - run tests that whose specs have newer modification time\n\n"
        "  not_pass - run tests whose status is not 'SUCCESS' (default)",
    )
