# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

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
from .testspec import ResolvedSpec

if TYPE_CHECKING:
    from .ir import DependencySpec


@dataclass(frozen=True, slots=True)
class ResolveContext:
    matchable_specs: list["JobSpecIR | ResolvedSpec"]
    unique_name_idx: dict[str, str]
    non_unique_idx: dict[str, list[str]]
    spec_map: dict[str, "JobSpecIR | ResolvedSpec"]


def _resolve_empty(spec: "JobSpecIR") -> tuple[str, list[str]]:
    return (spec.id, [])


def _find_matching_specs(
    dp: "DependencySpec",
    source_spec: "JobSpecIR",
    ctx: ResolveContext,
) -> list["JobSpecIR | ResolvedSpec"]:
    matches: set[str] = set()
    matched_specs: list["JobSpecIR | ResolvedSpec"] = []

    for pattern in shlex.split(dp.pattern):
        # Check exact matches first before resorting to glob matching
        candidates: list["JobSpecIR | ResolvedSpec"] = []
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

        if not matched_specs:
            # Glob pattern - check all matchable specs (ir AND resolved)
            for spec in ctx.matchable_specs:
                if spec.id == source_spec.id or spec.id in matches:
                    continue
                if dp.matches(spec):
                    matches.add(spec.id)
                    matched_specs.append(spec)

    return matched_specs


def _resolve_spec_dependencies(
    spec: "JobSpecIR",
    ctx: ResolveContext,
) -> tuple[str, list[str]]:
    matches: list[str] = []
    for dp in spec.dependencies:
        deps = _find_matching_specs(dp, spec, ctx)
        dep_ids = [d.id for d in deps]
        # Phase 1 keeps existing behavior:
        dp.update(*dep_ids)
        matches.extend(dep_ids)
    return (spec.id, matches)


def _resolve_dependencies_serial(
    specs_to_resolve: list["JobSpecIR"],
    ctx: ResolveContext,
) -> list[tuple[str, list[str]]]:
    results: list[tuple[str, list[str]]] = []
    for spec in specs_to_resolve:
        if not spec.dependencies:
            results.append(_resolve_empty(spec))
        else:
            results.append(_resolve_spec_dependencies(spec, ctx))
    return results


def _resolve_dependencies_parallel(
    specs_to_resolve: list["JobSpecIR"],
    ctx: ResolveContext,
) -> list[tuple[str, list[str]]]:
    if not specs_to_resolve:
        return []

    num_workers = min(os.cpu_count() or 4, len(specs_to_resolve))
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for spec in specs_to_resolve:
            if not spec.dependencies:
                futures.append(executor.submit(_resolve_empty, spec))
            else:
                futures.append(executor.submit(_resolve_spec_dependencies, spec, ctx))

        results: list[tuple[str, list[str]]] = []
        for future in as_completed(futures):
            results.append(future.result())
    return results


class DependencyResolver:
    """Phase-1 wrapper around the existing optimized resolution functions."""

    def __init__(self, specs: list["JobSpecIR | ResolvedSpec"]) -> None:
        self.specs = specs
        self.ctx = self._build_context(specs)

    @staticmethod
    def _build_context(specs: list["JobSpecIR | ResolvedSpec"]) -> ResolveContext:
        ir_specs: list[JobSpecIR] = []
        resolved_specs: list[ResolvedSpec] = []
        spec_map: dict[str, JobSpecIR | ResolvedSpec] = {}

        unique_name_idx: dict[str, str] = {}
        non_unique_idx: dict[str, list[str]] = defaultdict(list)

        for spec in specs:
            spec_map[spec.id] = spec
            if isinstance(spec, ResolvedSpec):
                resolved_specs.append(spec)
            else:
                ir_specs.append(spec)

            unique_name_idx[spec.id] = spec.id
            non_unique_idx[spec.name].append(spec.id)
            non_unique_idx[spec.family].append(spec.id)
            non_unique_idx[str(spec.file_path)].append(spec.id)

        matchable_specs = ir_specs + resolved_specs
        return ResolveContext(matchable_specs, unique_name_idx, non_unique_idx, spec_map)

    def resolve(self, ir_specs: list["JobSpecIR"]) -> list[tuple[str, list[str]]]:
        if os.getenv("CANARY_SERIAL_SPEC_RESOLUTION"):
            return _resolve_dependencies_serial(ir_specs, self.ctx)
        return _resolve_dependencies_parallel(ir_specs, self.ctx)


def resolve(specs: Sequence["JobSpecIR | ResolvedSpec"]) -> list["ResolvedSpec"]:
    # Separate specs into resolved and IR, and build a spec_map
    ir_specs: list[JobSpecIR] = []
    resolved_specs: list[ResolvedSpec] = []
    spec_map: dict[str, JobSpecIR | ResolvedSpec] = {}

    for spec in specs:
        spec_map[spec.id] = spec
        if isinstance(spec, ResolvedSpec):
            resolved_specs.append(spec)
        elif not spec.dependencies:
            # no dependencies -> can finalize immediately
            resolved_specs.append(spec.finalize({}))
        else:
            ir_specs.append(spec)

    # Build initial dependency graph from already-resolved specs
    graph: dict[str, list[str]] = {
        r.id: [d.spec.id for d in r.dependencies] for r in resolved_specs
    }

    # Resolve dependency patterns for all IR specs (fills dp.resolves_to in phase 1)
    resolver = DependencyResolver(list(specs))
    results = resolver.resolve(ir_specs)  # list[(spec_id, match_ids)]

    # Merge results into the graph
    for spec_id, matches in results:
        graph[spec_id] = matches
    for spec in specs:
        graph.setdefault(spec.id, [])

    # Topologically finalize IR specs
    lookup: dict[str, ResolvedSpec] = {}
    ts = TopologicalSorter(graph)
    ts.prepare()

    while ts.is_active():
        ids = ts.get_ready()
        for id in ids:
            node = spec_map[id]
            if isinstance(node, ResolvedSpec):
                lookup[id] = node
            else:
                assert isinstance(node, JobSpecIR)
                lookup[id] = node.finalize(lookup)
        ts.done(*ids)

    return list(lookup.values())
