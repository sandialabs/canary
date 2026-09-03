# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Dependency resolution: match :class:`~_canary.ir.DependencySelector` patterns to spec IDs.

The entry point is :func:`resolve`, which accepts a mixed list of already-resolved
:class:`~_canary.jobspec.JobSpec` objects and unresolved
:class:`~_canary.ir.JobSpecIR` objects, matches each IR spec's dependency
patterns against the full collection, and returns a fully resolved list of
``JobSpec`` objects in topological order.

Internally, :class:`DependencyResolver` uses either serial or parallel pattern
matching (controlled by the ``CANARY_SERIAL_SPEC_RESOLUTION`` environment
variable) and then finalises each IR spec via
:meth:`~_canary.ir.JobSpecIR.finalize` in topological order.
"""

import os
import shlex
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from dataclasses import dataclass
from graphlib import TopologicalSorter
from typing import TYPE_CHECKING
from typing import Sequence

from .ir import JobSpecIR
from .jobspec import JobSpec

if TYPE_CHECKING:
    from .ir import DependencySelector


@dataclass(frozen=True, slots=True)
class ResolveContext:
    """Pre-built lookup indexes used during pattern matching.

    Attributes:
        matchable_specs: All specs (IR + resolved) eligible to be matched as
            dependency targets.
        unique_name_idx: Mapping of spec ID → spec ID (identity lookup for
            full-ID matches).
        non_unique_idx: Mapping of name/family/file_path → list of spec IDs
            (used when a pattern matches by name rather than ID).
        spec_map: Mapping of spec ID → spec object for O(1) retrieval.
    """

    matchable_specs: list["JobSpecIR | JobSpec"]
    unique_name_idx: dict[str, str]
    non_unique_idx: dict[str, list[str]]
    spec_map: dict[str, "JobSpecIR | JobSpec"]


def _find_matching_specs(
    dp: "DependencySelector", source_spec: "JobSpecIR", ctx: ResolveContext
) -> list["JobSpecIR | JobSpec"]:
    """Return all specs that match *dp*'s pattern, excluding *source_spec* itself.

    Tries exact-name lookup first (O(1)) before falling back to glob matching
    over all matchable specs.  Multiple space-separated patterns in
    ``dp.pattern`` are evaluated independently and their results merged.

    Args:
        dp: The dependency selector containing the pattern and ``expects`` count.
        source_spec: The spec that owns this dependency (excluded from matches).
        ctx: Pre-built lookup context.

    Returns:
        Deduplicated list of matching specs in encounter order.
    """
    matches: set[str] = set()
    matched_specs: list["JobSpecIR | JobSpec"] = []

    for pattern in shlex.split(dp.pattern):
        matched_this_pattern: bool = False
        # Check exact matches first before resorting to glob matching
        candidates: list["JobSpecIR | JobSpec"] = []
        if pattern in ctx.unique_name_idx:
            spec_id = ctx.unique_name_idx[pattern]
            candidates.append(ctx.spec_map[spec_id])
        elif pattern in ctx.non_unique_idx:
            spec_ids = ctx.non_unique_idx[pattern]
            candidates.extend([ctx.spec_map[spec_id] for spec_id in spec_ids])

        for spec in candidates:
            if spec.id != source_spec.id and spec.id not in matches:
                matches.add(spec.id)
                matched_specs.append(spec)
                matched_this_pattern = True

        if not matched_this_pattern:
            # Glob pattern - check all matchable specs (ir AND resolved)
            for spec in ctx.matchable_specs:
                if spec.id == source_spec.id or spec.id in matches:
                    continue
                if dp.matches(spec):
                    matches.add(spec.id)
                    matched_specs.append(spec)

    return matched_specs


def _resolve_dependencies_serial(
    specs_to_resolve: list["JobSpecIR"], ctx: ResolveContext
) -> tuple[dict[str, list[str]], dict[str, list[tuple[int, list[str]]]], list[str]]:
    """Resolve dependency patterns for *specs_to_resolve* sequentially.

    Args:
        specs_to_resolve: IR specs whose dependencies need resolution.
        ctx: Pre-built lookup context.

    Returns:
        A three-tuple of:
        - ``edges_by_id``: ``{spec_id: [dep_id, ...]}`` flat dependency lists.
        - ``groups_by_id``: ``{spec_id: [(dep_index, [dep_id, ...]), ...]}``
          grouped by dependency selector index.
        - ``errors``: List of error strings from :meth:`~_canary.ir.DependencySelector.verify`.
    """
    edges_by_id: dict[str, list[str]] = {}
    groups_by_id: dict[str, list[tuple[int, list[str]]]] = {}
    errors: list[str] = []

    for spec in specs_to_resolve:
        if not spec.dependencies:
            edges_by_id[spec.id] = []
            groups_by_id[spec.id] = []
            continue

        flat: list[str] = []
        groups: list[tuple[int, list[str]]] = []

        for i, dp in enumerate(spec.dependencies):
            deps = _find_matching_specs(dp, spec, ctx)
            dep_ids = [d.id for d in deps]
            errors.extend(dp.verify(len(dep_ids)))
            groups.append((i, dep_ids))
            flat.extend(dep_ids)

        edges_by_id[spec.id] = flat
        groups_by_id[spec.id] = groups

    return edges_by_id, groups_by_id, errors


def _resolve_dependencies_parallel(
    specs_to_resolve: list["JobSpecIR"], ctx: ResolveContext
) -> tuple[dict[str, list[str]], dict[str, list[tuple[int, list[str]]]], list[str]]:
    """Resolve dependency patterns for *specs_to_resolve* using a thread pool.

    Parallelises :func:`_find_matching_specs` calls across
    ``min(cpu_count, len(specs_to_resolve))`` threads.  Safe because the
    context is read-only during resolution.

    Returns the same three-tuple as :func:`_resolve_dependencies_serial`.
    """
    if not specs_to_resolve:
        return {}, {}, []

    def work(spec: "JobSpecIR") -> tuple[str, list[str], list[tuple[int, list[str]]], list[str]]:
        if not spec.dependencies:
            return spec.id, [], [], []

        flat: list[str] = []
        groups: list[tuple[int, list[str]]] = []
        errs: list[str] = []

        for i, dp in enumerate(spec.dependencies):
            deps = _find_matching_specs(dp, spec, ctx)
            dep_ids = [d.id for d in deps]
            errs.extend(dp.verify(len(dep_ids)))
            groups.append((i, dep_ids))
            flat.extend(dep_ids)

        return spec.id, flat, groups, errs

    num_workers = min(os.cpu_count() or 4, len(specs_to_resolve))
    edges_by_id: dict[str, list[str]] = {}
    groups_by_id: dict[str, list[tuple[int, list[str]]]] = {}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(work, spec) for spec in specs_to_resolve]
        for fut in as_completed(futures):
            spec_id, flat, groups, errs = fut.result()
            edges_by_id[spec_id] = flat
            groups_by_id[spec_id] = groups
            errors.extend(errs)

    return edges_by_id, groups_by_id, errors


class DependencyResolver:
    """Stateful resolver that builds lookup indexes once and resolves many IR specs.

    Useful when resolution needs to be performed in multiple passes (e.g. when
    new IR specs are added incrementally).

    Args:
        specs: The full collection of specs (IR + already-resolved) to use as
            the dependency match pool.
    """

    def __init__(self, specs: list["JobSpecIR | JobSpec"]) -> None:
        self.specs = specs
        self.ctx = self._build_context(specs)

    @staticmethod
    def _build_context(specs: list["JobSpecIR | JobSpec"]) -> ResolveContext:
        """Build the :class:`ResolveContext` lookup tables from *specs*."""
        ir_specs: list[JobSpecIR] = []
        resolved_specs: list[JobSpec] = []
        spec_map: dict[str, JobSpecIR | JobSpec] = {}

        unique_name_idx: dict[str, str] = {}
        non_unique_idx: dict[str, list[str]] = defaultdict(list)

        for spec in specs:
            spec_map[spec.id] = spec
            if isinstance(spec, JobSpec):
                resolved_specs.append(spec)
            else:
                ir_specs.append(spec)

            unique_name_idx[spec.id] = spec.id
            non_unique_idx[spec.name].append(spec.id)
            non_unique_idx[spec.family].append(spec.id)
            non_unique_idx[str(spec.file_path)].append(spec.id)

        matchable_specs = ir_specs + resolved_specs
        return ResolveContext(matchable_specs, unique_name_idx, non_unique_idx, spec_map)

    def resolve(
        self, ir_specs: list["JobSpecIR"]
    ) -> tuple[dict[str, list[str]], dict[str, list[tuple[int, list[str]]]], list[str]]:
        """Resolve dependency patterns for *ir_specs*.

        Selects serial or parallel resolution based on the
        ``CANARY_SERIAL_SPEC_RESOLUTION`` environment variable.

        Args:
            ir_specs: The IR specs to resolve (must be a subset of the specs
                passed to the constructor).

        Returns:
            The same three-tuple as :func:`_resolve_dependencies_serial`.
        """
        if os.getenv("CANARY_SERIAL_SPEC_RESOLUTION"):
            return _resolve_dependencies_serial(ir_specs, self.ctx)
        return _resolve_dependencies_parallel(ir_specs, self.ctx)


def resolve(specs: Sequence["JobSpecIR | JobSpec"]) -> list["JobSpec"]:
    """Resolve all dependency patterns and return fully constructed ``JobSpec`` objects.

    This is the primary entry point for dependency resolution.  It:

    1. Separates already-resolved ``JobSpec`` objects from unresolved
       ``JobSpecIR`` objects.
    2. IR specs with no dependencies are finalised immediately.
    3. :class:`DependencyResolver` matches patterns for the remaining IR specs.
    4. IR specs are finalised in topological order so that upstream
       dependencies are available as ``JobSpec`` objects when a downstream
       spec calls :meth:`~_canary.ir.JobSpecIR.finalize`.

    Args:
        specs: Mixed sequence of ``JobSpec`` and ``JobSpecIR`` objects.

    Returns:
        All specs as fully resolved ``JobSpec`` objects in topological order.

    Raises:
        UnresolvedDependenciesErrors: If any dependency patterns could not be
            matched according to their ``expects`` constraints.
    """
    # Separate specs into resolved and IR, and build a spec_map
    ir_specs: list[JobSpecIR] = []
    resolved_specs: list[JobSpec] = []
    spec_map: dict[str, JobSpecIR | JobSpec] = {}

    for spec in specs:
        spec_map[spec.id] = spec
        if isinstance(spec, JobSpec):
            resolved_specs.append(spec)
        elif not spec.dependencies:
            # no dependencies -> can finalize immediately
            resolved_specs.append(spec.finalize({}, []))
        else:
            ir_specs.append(spec)

    # Build initial dependency graph from already-resolved specs
    graph: dict[str, list[str]] = {
        r.id: [d.spec.id for d in r.dependencies] for r in resolved_specs
    }

    # Resolve dependency patterns for all IR specs
    resolver = DependencyResolver(list(specs))
    edges_by_id, groups_by_id, errors = resolver.resolve(ir_specs)

    for spec_id, edges in edges_by_id.items():
        graph[spec_id] = edges
    # Ensure every node is present in graph
    for spec in specs:
        graph.setdefault(spec.id, [])

    if errors:
        raise UnresolvedDependenciesErrors(errors)

    # Topologically finalize IR specs
    lookup: dict[str, JobSpec] = {}
    ts = TopologicalSorter(graph)
    ts.prepare()

    while ts.is_active():
        ids = ts.get_ready()
        for id in ids:
            node = spec_map[id]
            if isinstance(node, JobSpec):
                lookup[id] = node
            else:
                assert isinstance(node, JobSpecIR)
                lookup[id] = node.finalize(lookup, groups_by_id.get(id, []))
        ts.done(*ids)

    return list(lookup.values())


class UnresolvedDependenciesErrors(Exception):
    """Raised when one or more dependency patterns could not be matched.

    Attributes:
        errors: List of individual error messages, one per failed pattern.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))
