# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Rerun strategies: which previously-known jobs a new ``canary run`` executes.

A *rerun strategy* answers one question — "given the results of the previous
session, which jobs should run this time?" — at two points in the pipeline:

1. **Root selection** (this module): query the workspace database for the spec
   IDs that seed the run.  :func:`get_specs` expands those seeds into a closed
   spec list via :func:`compute_rerun_closure` (downstream dependents are added
   and run; upstream prerequisites are loaded but masked).
2. **Runtime masking** (:class:`~_canary.core.rules.RerunRule`): after jobs are
   reconstructed, mask the ones the strategy says should not run.

Both points share a single :class:`Strategy` definition so their behavior
cannot drift.  A strategy therefore owns three things: its ``name``, its help
text, and the two predicates :meth:`Strategy.selects_root` (over a
:class:`~_canary.database.PartialSpec`) and :meth:`Strategy.should_run` (over a
runtime :class:`~_canary.core.job.Job`).

Built-in strategies:

- ``all`` — run every spec in the workspace (or tag).
- ``not_pass`` *(default)* — run specs whose latest result is not a pass
  (failed, diffed, timed out, aborted, or never run).
- ``failed`` — run specs whose latest result failed.
- ``not_run`` — run specs that have never produced a result.
- ``changed`` — run specs whose source file changed since the last run.
"""

from typing import TYPE_CHECKING
from typing import Iterable
from typing import Literal

from .core.jobspec import Mask
from .database import PartialSpec
from .database import WorkspaceDatabase

if TYPE_CHECKING:
    from .core.job import Job
    from .core.jobspec import JobSpec


StrategyType = Literal["all", "not_pass", "failed", "not_run", "changed"]

# Category name of a passing result.  ``PartialSpec.result_category`` stores the
# string name of the latest result's ``Category``; PASS covers SUCCESS as well
# as the expected-failure outcomes (XFAIL/XDIFF).
_PASS = "PASS"  # nosec B105 - result Category name, not a secret
_FAIL = "FAIL"
_NEVER_RUN = (None, "NONE")


class Strategy:
    """A named rerun strategy shared by root selection and runtime masking.

    Subclasses implement :meth:`selects_root` and :meth:`should_run`; the two
    must encode the same intent so that the set of jobs seeded from the database
    matches the set left unmasked at runtime.  Where the two layers must differ
    (for example, ``failed`` seeds BLOCKED specs so they load, but relies on
    mask propagation rather than the rule to re-run them), the difference is
    documented on the strategy itself.
    """

    name: str
    help: str

    def selects_root(self, pspec: "PartialSpec") -> bool:
        """Return ``True`` if *pspec* should seed the rerun (root selection)."""
        raise NotImplementedError

    def should_run(self, job: "Job") -> "RunDecision":
        """Return whether *job* should run, with a reason when it should not."""
        raise NotImplementedError


class RunDecision:
    """Result of :meth:`Strategy.should_run`: run the job, or skip it with a reason."""

    __slots__ = ("run", "reason")

    def __init__(self, run: bool, reason: str | None = None) -> None:
        self.run = run
        self.reason = reason

    def __bool__(self) -> bool:
        return self.run


STRATEGIES: dict[str, Strategy] = {}


def register(strategy: Strategy) -> Strategy:
    """Register *strategy* under its ``name`` in :data:`STRATEGIES`."""
    if strategy.name in STRATEGIES:
        raise RuntimeError(f"Duplicate rerun strategy: {strategy.name}")
    STRATEGIES[strategy.name] = strategy
    return strategy


def get_strategy(name: str) -> Strategy:
    """Return the registered :class:`Strategy` named *name*.

    Raises:
        ValueError: If *name* is not a registered strategy.
    """
    try:
        return STRATEGIES[name]
    except KeyError:
        raise ValueError(f"Unknown rerun strategy: {name!r}") from None


class _All(Strategy):
    name = "all"
    help = "run all selected tests, even if they already passed"

    def selects_root(self, pspec: "PartialSpec") -> bool:
        return True

    def should_run(self, job: "Job") -> RunDecision:
        return RunDecision(True)


class _NotPass(Strategy):
    name = "not_pass"
    help = "run tests whose latest result did not pass (default)"

    def selects_root(self, pspec: "PartialSpec") -> bool:
        return pspec.result_category != _PASS

    def should_run(self, job: "Job") -> RunDecision:
        if not job.status.is_success():
            return RunDecision(True)
        return RunDecision(False, reason=f"previous result = {job.status.outcome.name}")


class _Failed(Strategy):
    name = "failed"
    help = "run only tests whose latest result failed"

    def selects_root(self, pspec: "PartialSpec") -> bool:
        # Seed FAIL specs directly, and BLOCKED specs so they are loaded; a
        # BLOCKED downstream is re-run via mask propagation from its (re-run)
        # failed upstream rather than by should_run below.
        return pspec.result_category == _FAIL or pspec.result_outcome == "BLOCKED"

    def should_run(self, job: "Job") -> RunDecision:
        if job.status.is_failure():
            return RunDecision(True)
        return RunDecision(False, reason=f"previous result = {job.status.outcome.name} != FAIL")


class _NotRun(Strategy):
    name = "not_run"
    help = "run only tests that have never been executed"

    def selects_root(self, pspec: "PartialSpec") -> bool:
        return pspec.result_category in _NEVER_RUN

    def should_run(self, job: "Job") -> RunDecision:
        if job.status.is_unset():
            return RunDecision(True)
        return RunDecision(False, reason=f"previous result = {job.status.category!r}")


class _Changed(Strategy):
    name = "changed"
    help = "run tests whose source file changed since the last run"

    def selects_root(self, pspec: "PartialSpec") -> bool:
        mtime = pspec.file.stat().st_mtime
        # A never-run spec (started_at <= 0) has no prior run to compare
        # against, so it is treated as changed and seeded.
        return pspec.started_at <= 0 or mtime > pspec.started_at

    def should_run(self, job: "Job") -> RunDecision:
        started = job.timekeeper._started
        if started < 0 or job.spec.file.stat().st_mtime > started:
            return RunDecision(True)
        return RunDecision(False, reason="job spec has not changed since last run")


register(_All())
register(_NotPass())
register(_Failed())
register(_NotRun())
register(_Changed())


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
        A list of :class:`~_canary.core.jobspec.JobSpec` objects.  Upstream specs
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
        strategy: Name of a registered rerun strategy (see :data:`STRATEGIES`).
        tag: Optional workspace tag to restrict the query to a named selection.

    Returns:
        Expanded rerun spec list; empty list if the strategy selects no roots.

    Raises:
        ValueError: If *strategy* is not a registered strategy name.
    """
    strat = get_strategy(strategy)
    pspecs = db.get_partial_specs(tag=tag)
    roots = {pspec.id for pspec in pspecs if strat.selects_root(pspec)}
    if not roots:
        return []
    return compute_rerun_closure(db, roots=roots)


def only_help() -> str:
    """Return the ``--only`` help text, one aligned line per strategy."""
    order = ("all", "failed", "not_run", "changed", "not_pass")
    width = max(len(name) for name in order)
    lines = ["Which previously-known tests to run after selection\n"]
    lines.extend(f"  {STRATEGIES[name].name:<{width}} - {STRATEGIES[name].help}" for name in order)
    return "\n\n".join(lines)


def setup_parser(parser) -> None:
    """Add the ``--only`` argument for choosing a rerun strategy to *parser*.

    The default is left as ``None`` so callers can distinguish an explicit
    ``--only`` from the unset case; ``run`` resolves the effective default
    (``not_pass`` in general, ``all`` when re-running specific tests by ID or
    view path).
    """
    parser.add_argument(
        "--only",
        dest="only",
        choices=sorted(STRATEGIES.keys()),
        default=None,
        help=only_help() + "\n\n  [default: not_pass]",
    )
