# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Canary Generate Pipeline
========================

This module implements the generateion lifecycle for converting generator output into fully resolved
test specs. The central orchestrator is the ``Generator`` object, which progresses through
validation, resolution, and finally hook-driven post-processing.

The ``canary_generate(generator)`` function coordinates the entire process using Pluggy hooks.  Plugins
may observe or modify the generate at specific stages.

Flow Diagram
------------

The following diagram illustrates the full lifecycle::

  Generator(s)
    Produces [Un]resolved test specs
                      ↓
  Generator(generators)
    Generate UnresolvedSpec from generator outputs
                      ↓
  canary_generate(generators)
  • pluginmanager.hook.canary_generatestart()
  • generator.run()
    • validate(...)
    • resolve(...)
  • pluginmanager.hook.canary_generate_modifiyitems()
  • pluginmanager.hook.canary_generate_report()
  → generator.resolved_specs()

"""

import fnmatch
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from graphlib import TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Iterable
from typing import Sequence

import rich.box
from rich.console import Console
from rich.table import Table

from . import config
from .hookspec import hookimpl
from .util import logging
from .util.string import pluralize

if TYPE_CHECKING:
    from .config.argparsing import Parser
    from .generator import AbstractTestGenerator
    from .testspec import DependencyPatterns
    from .testspec import ResolvedSpec
    from .testspec import UnresolvedSpec


logger = logging.get_logger(__name__)


class Generator:
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

    def run(self) -> list["ResolvedSpec"]:
        pm = logger.progress_monitor("[bold]Generating[/] test specs from generators")
        config.pluginmanager.hook.canary_generatestart(generator=self)
        drafts: list["UnresolvedSpec | ResolvedSpec"] = generate_test_specs(
            self.generators, self.on_options
        )
        pm.done()
        self.validate(drafts)
        pm = logger.progress_monitor("[bold]Resolving[/] test spec dependencies")
        self.specs = resolve(drafts)
        self.ready = True
        pm.done()
        config.pluginmanager.hook.canary_generate_modifyitems(generator=self)
        config.pluginmanager.hook.canary_generate_report(generator=self)
        return self.specs

    def validate(self, specs: list["UnresolvedSpec | ResolvedSpec"]) -> None:
        pm = logger.progress_monitor("[bold]Searching[/] for duplicated tests")
        ids = [spec.id for spec in specs]
        counts: dict[str, int] = {}
        for id in ids:
            counts[id] = counts.get(id, 0) + 1
        duplicate_ids = {id for id, count in counts.items() if count > 1}
        duplicates: dict[str, list["UnresolvedSpec | ResolvedSpec"]] = {}
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
        pm.done()
        return None

    @staticmethod
    def setup_parser(parser: "Parser") -> None:
        group = parser.add_argument_group("test spec generation")
        group.add_argument(
            "-o",
            dest="on_options",
            default=None,
            metavar="option",
            action="append",
            help="Turn option(s) on, such as '-o dbg' or '-o intel'",
        )


@hookimpl
def canary_generate_report(generator: Generator) -> None:
    nc, ng = len(generator.specs), len(generator.generators)
    logger.info("[bold]Generated[/] %d test specs from %d generators" % (nc, ng))
    excluded = [spec for spec in generator.specs if spec.mask]
    if excluded:
        n = len(excluded)
        logger.info("[bold]Excluded[/] %d test %s during generation" % (n, pluralize("spec", n)))
        table = Table(show_header=True, header_style="bold", box=rich.box.SIMPLE_HEAD)
        table.add_column("Reason", no_wrap=True)
        table.add_column("Count", justify="right")
        reasons: dict[str | None, list["ResolvedSpec"]] = {}
        for spec in excluded:
            reasons.setdefault(spec.mask.reason, []).append(spec)
        keys = sorted(reasons, key=lambda x: len(reasons[x]))
        for key in reversed(keys):
            reason = key if key is None else key.lstrip()
            table.add_row(reason, str(len(reasons[key])))
        console = Console(file=sys.stderr)
        console.print(table)


def resolve(specs: Sequence["UnresolvedSpec | ResolvedSpec"]) -> list["ResolvedSpec"]:
    from .testspec import ResolvedSpec
    from .testspec import UnresolvedSpec

    # Separate specs into resolved and draft
    draft_specs: list["UnresolvedSpec"] = []
    resolved_specs: list["ResolvedSpec"] = []
    spec_map: dict[str, "UnresolvedSpec | ResolvedSpec"] = {}

    # Generator indices
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

    # Generator dependency graph in parallel, specs will be added as they resolve
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


def _generate_specs(
    file: "AbstractTestGenerator", on_options: list[str] | None
) -> list["UnresolvedSpec | ResolvedSpec"]:
    try:
        logging.filter_warnings(bool(getattr(file, "filter_warnings", False)))
        return list(file.lock(on_options=on_options))
    finally:
        logging.filter_warnings(False)


def generate_test_specs(
    generators: list["AbstractTestGenerator"], on_options: list[str]
) -> list["UnresolvedSpec | ResolvedSpec"]:
    if config.get("debug"):
        return generate_test_specs_serial(generators, on_options)
    return generate_test_specs_parallel(generators, on_options)


def generate_test_specs_parallel(
    generators: list["AbstractTestGenerator"], on_options: list[str]
) -> list["UnresolvedSpec | ResolvedSpec"]:
    specs: list["UnresolvedSpec | ResolvedSpec"] = []
    errors = 0
    with ThreadPoolExecutor() as ex:
        futures = {ex.submit(_generate_specs, f, on_options): f for f in generators}
        for future in as_completed(futures):
            try:
                specs.extend(future.result())
            except Exception:
                errors += 1
                logger.exception(f"Generator failed: {futures[future]}")
    if errors:
        raise ValueError("Failed to generate specs from one or more generators")
    return specs


def generate_test_specs_serial(
    generators: list["AbstractTestGenerator"], on_options: list[str]
) -> list["UnresolvedSpec | ResolvedSpec"]:
    locked: list[list["UnresolvedSpec | ResolvedSpec"]] = []
    for f in generators:
        locked.append(_generate_specs(f, on_options))
    return [spec for group in locked for spec in group]
