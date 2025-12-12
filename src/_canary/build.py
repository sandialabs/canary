# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Canary Build Pipeline
=====================

This module implements the build lifecycle for converting generator output into fully resolved test
specifications.  The central orchestrator is the ``Builder`` object, which progresses through
validation, resolution, and finally hook-driven post-processing.

The ``canary_build(builder)`` function coordinates the entire process using Pluggy hooks.  Plugins
may observe or modify the build at specific stages.

Flow Diagram
------------

The following diagram illustrates the full lifecycle:

    +--------------------------------------------------+
    |  Generator(s)                                    |
    |    Produces [Un]resolved test specs              |
    |                      ↓                           |
    |  Builder(generators)                             |
    |    Build UnresolvedSpec from generator outputs   |
    |                      ↓                           |
    |  canary_build(builder)                           |
    |  • pluginmanager.hook.canary_buildstart()        |
    |  • builder.run()                                 |
    |    • validate(...)                               |
    |    • resolve(...)                                |
    |  • pluginmanager.hook.canary_build_modifyitems() |
    |  • pluginmanager.hook.canary_build_report()      |
    |  → builder.resolved_specs()                      |
    +--------------------------------------------------+


Functions
---------

canary_build(builder)
    Runs the full build pipeline.

    Args:
        builder (Builder): The builder instance containing generator output.

    Returns:
        list[ResolvedSpec]: The fully resolved and optionally plugin-modified
        final specifications.

    Lifecycle:
        1. ``canary_buildstart(builder)``
           Invoked before any processing. Plugins may inspect or adjust
           input material.

        2. ``builder.run()``
           Runs validation and resolution.

        3. ``canary_build_modifyitems(builder)``
           Invoked after resolution. Plugins may modify resolved items before
           finalization.

        4. ``canary_build_report(builder)``
           Invoked after modifications. Plugins may output or record final
           information but should not mutate data.

        5. Return ``builder.resolved_specs()``.


Classes
-------

class Builder:
    Coordinates conversion from raw generator output into resolved specs.

    Methods:
        run():
            Performs the two essential phases:

            * validate(unresolved)
              Ensures UnresolvedSpecs are structurally and semantically valid.

            * resolve(unresolved)
              Produces concrete resolved specs suitable for test execution.

        resolved_specs():
            Returns the final list of resolved ResolvedSpec after all hooks have executed.


Hook Specifications
-------------------

Plugins may implement the following hooks:

canary_buildstart(builder):
    Called before ``builder.run()``. Plugins may modify the builder or its inputs.

canary_build_modifyitems(builder):
    Called after resolution. Plugins may reorder, mutate, filter, or otherwise modify resolved
    specs.

canary_build_report(builder):
    Called after modifications. Plugins should emit reports or summaries but generally should not
    perform further mutation.

"""

import fnmatch
import hashlib
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
from graphlib import TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Iterable
from typing import Sequence

from . import config
from .hookspec import hookimpl
from .util import json_helper as json
from .util import logging
from .util.parallel import starmap

if TYPE_CHECKING:
    from .generator import AbstractTestGenerator
    from .testspec import DependencyPatterns
    from .testspec import ResolvedSpec
    from .testspec import UnresolvedSpec


logger = logging.get_logger(__name__)


class Builder:
    def __init__(
        self,
        generators: list["AbstractTestGenerator"],
        workspace: Path,
        on_options: Iterable[str] = (),
    ) -> None:
        self.generators = generators
        self.workspace = workspace
        self.on_options = list(on_options)
        self.specs: list["ResolvedSpec"] = []

    @cached_property
    def signature(self) -> str:
        parts = [str(generator.file) for generator in self.generators] + self.on_options
        parts.sort()
        signature = hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()
        return signature

    def run(self) -> list["ResolvedSpec"]:
        config.pluginmanager.hook.canary_buildstart(builder=self)
        locked: list[list["UnresolvedSpec"]] = []
        if config.get("debug"):
            for f in self.generators:
                locked.append(lock_file(f, self.on_options))
        else:
            locked.extend(starmap(lock_file, [(f, self.on_options) for f in self.generators]))
        drafts: list["UnresolvedSpec"] = [draft for group in locked for draft in group]
        self.validate(drafts)
        pm = logger.progress_monitor("@*{Resolving} test spec dependencies")
        self.specs = resolve(drafts)
        self.ready = True
        pm.done()
        config.pluginmanager.hook.canary_build_modifyitems(builder=self)
        config.pluginmanager.hook.canary_build_report(builder=self)
        return self.specs

    def validate(self, specs: list["UnresolvedSpec"]) -> None:
        logger.info("@*{Searching} for duplicated tests")
        ids = [spec.id for spec in specs]
        counts: dict[str, int] = {}
        for id in ids:
            counts[id] = counts.get(id, 0) + 1
        duplicate_ids = {id for id, count in counts.items() if count > 1}
        duplicates: dict[str, list["UnresolvedSpec"]] = {}
        # if there are duplicates, we are in error condition and lookup cost is not important
        for id in duplicate_ids:
            duplicates.setdefault(id, []).extend([_ for _ in specs if _.id == id])
        if duplicates:
            logger.error("Duplicate test IDs generated for the following test cases")
            for id, dspecs in duplicates.items():
                logger.error(f"{id}:")
                for spec in dspecs:
                    logger.log(
                        logging.EMIT,
                        f"  - {spec.display_name()}: {spec.file_path}",
                        extra={"prefix": ""},
                    )
            raise ValueError("Duplicate test IDs in test suite")
        return None


@hookimpl
def canary_build_report(builder: Builder) -> None:
    nc, ng = len(builder.specs), len(builder.generators)
    logger.info("@*{Generated} %d test specs from %d generators" % (nc, ng))


def lock_file(file: "AbstractTestGenerator", on_options: list[str] | None):
    return file.lock(on_options=on_options)


def resolve(specs: Sequence["UnresolvedSpec | ResolvedSpec"]) -> list["ResolvedSpec"]:
    from .testspec import ResolvedSpec
    from .testspec import UnresolvedSpec

    # Separate specs into resolved and draft
    draft_specs: list["UnresolvedSpec"] = []
    resolved_specs: list["ResolvedSpec"] = []
    spec_map: dict[str, "UnresolvedSpec | ResolvedSpec"] = {}

    # Build indices
    unique_name_idx: dict[str, str] = {}
    non_unique_idx: dict[str, list[str]] = defaultdict(list)

    for spec in specs:
        spec_map[spec.id] = spec

        if isinstance(spec, ResolvedSpec):
            resolved_specs.append(spec)
        else:
            draft_specs.append(spec)

        # Index unique identifiers (for both draft and resolved)
        unique_name_idx[spec.id] = spec.id

        # Index non-unique identifiers (for both draft and resolved)
        non_unique_idx[spec.name].append(spec.id)
        non_unique_idx[spec.family].append(spec.id)
        non_unique_idx[spec.display_name()].append(spec.id)
        non_unique_idx[spec.display_name(resolve=True)].append(spec.id)
        non_unique_idx[str(spec.file_path)].append(spec.id)

    # All specs that can be matched (both draft and resolved)
    matchable_specs = draft_specs + resolved_specs

    # Build dependency graph in parallel, specs will be added as they resolve
    graph: dict[str, list[str]] = {r.id: [_.id for _ in r.dependencies] for r in resolved_specs}
    draft_lookup: dict[str, list[str]] = {}
    dep_done_criteria: dict[str, list[str]] = {}

    results: list[tuple[str, list[str], list[str]]]
    if os.getenv("CANARY_SERIAL_SPEC_RESOLUTION"):
        results = _resolve_dependencies_serial(
            draft_specs, matchable_specs, unique_name_idx, non_unique_idx, spec_map
        )
    else:
        results = _resolve_dependencies_parallel(
            draft_specs, matchable_specs, unique_name_idx, non_unique_idx, spec_map
        )

    # Merge results
    for spec_id, matches, done_criteria in results:
        graph[spec_id] = matches
        draft_lookup[spec_id] = matches
        dep_done_criteria[spec_id] = done_criteria

    # Resolve dependencies using topological sort (this is fast, keep sequential)
    errors: defaultdict[str, list[str]] = defaultdict(list)
    lookup: dict[str, ResolvedSpec] = {}
    ts = TopologicalSorter(graph)
    ts.prepare()

    while ts.is_active():
        ids = ts.get_ready()
        for id in ids:
            draft = spec_map[id]
            if isinstance(draft, ResolvedSpec):
                lookup[id] = draft
            else:
                assert isinstance(draft, UnresolvedSpec)
                dep_ids = draft_lookup.get(id, [])
                dependencies = [lookup[dep_id] for dep_id in dep_ids]
                lookup[id] = draft.resolve(dependencies, dep_done_criteria.get(id, []))

        ts.done(*ids)

    return list(lookup.values())


def _resolve_dependencies_serial(
    specs_to_resolve: list["UnresolvedSpec"],
    matchable_specs: list["UnresolvedSpec | ResolvedSpec"],
    unique_name_idx: dict[str, str],
    non_unique_idx: dict[str, list[str]],
    spec_map: dict[str, "UnresolvedSpec | ResolvedSpec"],
) -> list[tuple[str, list[str], list[str]]]:
    """Resolve dependencies serially for debugging"""
    results = []
    for spec in specs_to_resolve:
        if not spec.dep_patterns:
            results.append(_resolve_empty(spec))
        else:
            results.append(
                _resolve_spec_dependencies(
                    spec, matchable_specs, unique_name_idx, non_unique_idx, spec_map
                )
            )
    return results


def _resolve_dependencies_parallel(
    specs_to_resolve: list["UnresolvedSpec"],
    matchable_specs: list["UnresolvedSpec | ResolvedSpec"],
    unique_name_idx: dict[str, str],
    non_unique_idx: dict[str, list[str]],
    spec_map: dict[str, "UnresolvedSpec | ResolvedSpec"],
) -> list[tuple[str, list[str], list[str]]]:
    """Resolve dependencies in parallel, returning (spec_id, match_ids, done_criteria)"""

    if not specs_to_resolve:
        return []

    num_workers = min(os.cpu_count() or 4, len(specs_to_resolve))

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for spec in specs_to_resolve:
            if not spec.dep_patterns:
                futures.append(executor.submit(_resolve_empty, spec))
            else:
                futures.append(
                    executor.submit(
                        _resolve_spec_dependencies,
                        spec,
                        matchable_specs,
                        unique_name_idx,
                        non_unique_idx,
                        spec_map,
                    )
                )

        results = [future.result() for future in futures]

    return results


def _resolve_empty(spec: "UnresolvedSpec") -> tuple[str, list[str], list[str]]:
    """Fast path for specs with no dependencies"""
    return (spec.id, [], [])


def _resolve_spec_dependencies(
    spec: "UnresolvedSpec",
    matchable_specs: list["UnresolvedSpec | ResolvedSpec"],
    unique_name_idx: dict[str, str],
    non_unique_idx: dict[str, list[str]],
    spec_map: dict[str, "UnresolvedSpec | ResolvedSpec"],
) -> tuple[str, list[str], list[str]]:
    """Resolve dependencies for a single spec"""
    matches: list[str] = []
    done_criteria: list[str] = []

    for dp in spec.dep_patterns:
        deps = _find_matching_specs(
            dp, spec, matchable_specs, unique_name_idx, non_unique_idx, spec_map
        )
        dep_ids = [d.id for d in deps]
        dp.update(*dep_ids)
        matches.extend(dep_ids)
        done_criteria.extend([dp.result_match] * len(deps))

    return (spec.id, matches, done_criteria)


def _find_matching_specs(
    dp: "DependencyPatterns",
    source_spec: "UnresolvedSpec",
    matchable_specs: list["UnresolvedSpec | ResolvedSpec"],
    unique_name_idx: dict[str, str],
    non_unique_idx: dict[str, list[str]],
    spec_map: dict[str, "UnresolvedSpec | ResolvedSpec"],
) -> list["UnresolvedSpec | ResolvedSpec"]:
    """Optimized pattern matching using indices where possible"""
    matches: set[str] = set()
    matched_specs: list["UnresolvedSpec | ResolvedSpec"] = []

    for pattern in dp.patterns:
        # Check exact matches first before resorting to glob matching
        candidates: list["UnresolvedSpec | ResolvedSpec"] = []
        if pattern in unique_name_idx:
            spec_id = unique_name_idx[pattern]
            candidates.append(spec_map[spec_id])
        elif pattern in non_unique_idx:
            spec_ids = non_unique_idx[pattern]
            candidates.extend([spec_map[spec_id] for spec_id in spec_ids])

        for spec in candidates:
            if spec.id != source_spec.id and spec.id not in matches:
                matches.add(spec.id)
                matched_specs.append(spec)

        if not matched_specs:
            # Glob pattern - check all matchable specs (draft AND resolved)
            for spec in matchable_specs:
                if spec.id == source_spec.id or spec.id in matches:
                    continue

                if _pattern_matches_spec(pattern, spec):
                    matches.add(spec.id)
                    matched_specs.append(spec)

    return matched_specs


def _pattern_matches_spec(pattern: str, spec: "UnresolvedSpec | ResolvedSpec") -> bool:
    """Check if pattern matches any of the spec's names"""
    names = (
        spec.id,
        spec.name,
        spec.family,
        spec.fullname,
        str(spec.file_path),
    )

    for name in names:
        if fnmatch.fnmatchcase(name, pattern):
            return True
    return False
