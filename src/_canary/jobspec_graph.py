# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Dependency graph construction and rendering helpers for :class:`~_canary.jobspec.JobSpec` objects.

Wraps :class:`~_canary.util.level_graph.LevelGraph` with spec-specific ID and
dependency accessor functions.  Also provides :func:`print_spec_graph` and
:func:`format_spec_graph` for rendering the dependency tree to text.
"""

import io
import sys
from typing import Iterable
from typing import Sequence
from typing import TextIO
from typing import TypeAlias

from .jobspec import JobSpec
from .util.level_graph import LevelGraph

SpecGraph: TypeAlias = LevelGraph[JobSpec]


def spec_id(spec: JobSpec) -> str:
    """Return the unique string ID for *spec* (used as the graph node key)."""
    return spec.id


def spec_dependencies(spec: JobSpec) -> Iterable[str]:
    """Yield the IDs of all specs that *spec* depends on."""
    for dep in spec.dependencies:
        yield dep.spec.id


def spec_sort_key(spec: JobSpec) -> tuple[str, str]:
    """Return a stable sort key for *spec* used to order nodes at the same level.

    Prefers ``fullname`` over ``name`` over ``id`` for human-readable ordering.
    """
    name = getattr(spec, "fullname", None) or getattr(spec, "name", None) or spec.id
    return str(name), spec.id


def make_spec_graph(specs: Sequence[JobSpec], *, require_closed: bool = True) -> SpecGraph:
    """Build a dependency graph from a flat sequence of :class:`~_canary.jobspec.JobSpec` objects.

    Args:
        specs: All specs to include in the graph.
        require_closed: If ``True`` (default), raise an error if any dependency
            reference points to a spec not present in *specs*.

    Returns:
        A :class:`~_canary.util.level_graph.LevelGraph` of specs in topological
        order.
    """
    return LevelGraph.from_items(
        specs,
        id_fn=spec_id,
        deps_fn=spec_dependencies,
        sort_key=spec_sort_key,
        require_closed=require_closed,
    )


def make_spec_graph_from_levels(
    levels: Sequence[Sequence[JobSpec]], *, require_closed: bool = True
) -> SpecGraph:
    """Build a dependency graph from an already-levelled sequence of spec groups.

    Args:
        levels: Sequence of spec groups where level *n* may depend on level *n-1*.
        require_closed: If ``True`` (default), raise an error for unresolved
            dependency references.

    Returns:
        A :class:`~_canary.util.level_graph.LevelGraph` of specs.
    """
    return LevelGraph.from_levels(
        levels, id_fn=spec_id, deps_fn=spec_dependencies, require_closed=require_closed
    )


def iter_downstream_specs(graph: SpecGraph) -> Iterable[JobSpec]:
    """Yield specs that are not dependencies of any other spec.

    These are the top-level specs to print when rendering dependency trees.
    """
    for spec in graph.topo_order():
        if not graph.dependents_by_id.get(spec.id):
            yield spec


def print_spec_graph(
    specs: Sequence[JobSpec],
    *,
    file: TextIO = sys.stdout,
    style: str = "none",
    level: int = -1,
    require_closed: bool = True,
) -> None:
    """Print the dependency tree for *specs* to *file*.

    Only top-level (downstream) specs are printed as roots; their upstream
    dependencies are rendered as indented children.

    Args:
        specs: Specs to include in the graph.
        file: Output stream; defaults to ``sys.stdout``.
        style: Rendering style passed through to :meth:`~_canary.jobspec.JobSpec.print`.
        level: Maximum depth to render (``-1`` for unlimited).
        require_closed: Forwarded to :func:`make_spec_graph`.
    """
    graph = make_spec_graph(specs, require_closed=require_closed)
    final_specs = list(iter_downstream_specs(graph))
    for i, spec in enumerate(final_specs):
        spec.print(level=level, file=file, end=i == len(final_specs) - 1, style=style)


def format_spec_graph(
    specs: Sequence[JobSpec], *, style: str = "none", level: int = -1, require_closed: bool = True
) -> str:
    """Return the dependency tree for *specs* as a string.

    Convenience wrapper around :func:`print_spec_graph` that captures the
    output to a ``StringIO`` buffer.

    Args:
        specs: Specs to include in the graph.
        style: Rendering style.
        level: Maximum depth (``-1`` for unlimited).
        require_closed: Forwarded to :func:`make_spec_graph`.
    """
    file = io.StringIO()
    print_spec_graph(specs, file=file, style=style, level=level, require_closed=require_closed)
    return file.getvalue()
