# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
from typing import Callable
from typing import Iterable
from typing import Literal

from .database import WorkspaceDatabase
from .testspec import Mask
from .testspec import ResolvedSpec

StrategyType = Literal["changed"]
STRATEGIES: dict[str, Callable[..., set[str]]] = {}


def compute_rerun_closure(db: WorkspaceDatabase, roots: Iterable[str]) -> list["ResolvedSpec"]:
    roots = set(roots)
    upstream, downstream = db.get_updownstream_ids(seeds=list(roots))
    runspecs = roots | downstream
    getspecs = runspecs | upstream
    resolved = db.load_specs(ids=list(getspecs))
    for spec in resolved:
        if spec.id not in runspecs:
            spec.mask = Mask(True, reason="Skip upstream specs")
    return resolved


def get_specs_from_view(
    db: WorkspaceDatabase,
    *,
    prefixes: list[str],
) -> list["ResolvedSpec"]:
    roots = db.select_from_view(prefixes=prefixes)
    return compute_rerun_closure(db, roots=roots)


def get_specs(
    db: WorkspaceDatabase,
    *,
    strategy: StrategyType,
    tag: str | None,
) -> list["ResolvedSpec"]:
    """
    Compute the full rerun spec set using a named strategy.

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
    name = fn.__name__
    if name in STRATEGIES:
        raise RuntimeError(f"Duplicate rerun strategy: {name}")
    STRATEGIES[name] = fn
    return fn


@rerun_strategy
def changed(
    db: WorkspaceDatabase,
    *,
    tag: str | None = None,
) -> set[str]:
    """
    Specs whose file mtime is newer than their latest result.
    """
    pspecs = db.get_partial_specs(tag=tag)
    ids: set[str] = set()
    for pspec in pspecs:
        mtime = pspec.file.stat().st_mtime
        if pspec.started_at > 0 and mtime > pspec.started_at:
            ids.add(pspec.id)
    return ids


@rerun_strategy
def not_pass(
    db: WorkspaceDatabase,
    *,
    tag: str | None = None,
) -> set[str]:
    """
    Specs with no result or non-PASS result.
    """
    ids: set[str] = set()
    pspecs = db.get_partial_specs(tag=tag)
    for pspec in pspecs:
        if pspec.result_category != "PASS":
            ids.add(pspec.id)
    return ids


@rerun_strategy
def failed(
    db: WorkspaceDatabase,
    *,
    tag: str | None = None,
) -> set[str]:
    """
    Specs whose latest result is FAIL.
    """
    ids: set[str] = set()
    pspecs = db.get_partial_specs(tag=tag)
    for pspec in pspecs:
        if pspec.result_category == "FAIL":
            ids.add(pspec.id)
    return ids


@rerun_strategy
def not_run(
    db: WorkspaceDatabase,
    *,
    tag: str | None = None,
) -> set[str]:
    """
    Specs whose latest result is FAIL.
    """
    ids: set[str] = set()
    pspecs = db.get_partial_specs(tag=tag)
    for pspec in pspecs:
        if pspec.result_category in (None, "NONE"):
            ids.add(pspec.id)
    return ids


@rerun_strategy
def all(
    db: WorkspaceDatabase,
    *,
    tag: str | None = None,
) -> set[str]:
    """
    Specs whose latest result is FAIL.
    """
    pspecs = db.get_partial_specs(tag=tag)
    return {c.id for c in pspecs}


def setup_parser(parser) -> None:
    parser.add_argument(
        "--only",
        dest="only",
        choices=STRATEGIES.keys(),
        default="not_pass",
        help="Which tests to run after selection\n\n"
        "  all      - run all selected tests, even if already passing\n\n"
        "  failed   - run only previously failing tests\n\n"
        "  not_run  - run tests that have never been executed\n\n"
        "  changed  - run tests that whose specs have newer modification time\n\n"
        "  not_pass - run tests whose status is not 'SUCCESS' (default)",
    )
