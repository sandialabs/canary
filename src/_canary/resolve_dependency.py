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


def _find_matching_specs(
    dp: "DependencySpec",
    source_spec: "JobSpecIR",
    ctx: ResolveContext,
) -> list["JobSpecIR | ResolvedSpec"]:
    matches: set[str] = set()
    matched_specs: list["JobSpecIR | ResolvedSpec"] = []

    for pattern in shlex.split(dp.pattern):
        matched_this_pattern: bool = False
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
    specs_to_resolve: list["JobSpecIR"],
    ctx: ResolveContext,
) -> tuple[
    dict[str, list[str]],
    dict[str, list[tuple[int, list[str]]]],
    list[str],
]:
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
    specs_to_resolve: list["JobSpecIR"],
    ctx: ResolveContext,
) -> tuple[
    dict[str, list[str]],
    dict[str, list[tuple[int, list[str]]]],
    list[str],
]:
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

    def resolve(
        self, ir_specs: list["JobSpecIR"]
    ) -> tuple[dict[str, list[str]], dict[str, list[tuple[int, list[str]]]], list[str]]:
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
                lookup[id] = node.finalize(lookup, groups_by_id.get(id, []))
        ts.done(*ids)

    return list(lookup.values())


class UnresolvedDependenciesErrors(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))
