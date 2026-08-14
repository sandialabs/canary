# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

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
    return spec.id


def spec_dependencies(spec: JobSpec) -> Iterable[str]:
    for dep in spec.dependencies:
        yield dep.spec.id


def spec_sort_key(spec: JobSpec) -> tuple[str, str]:
    name = getattr(spec, "fullname", None) or getattr(spec, "name", None) or spec.id
    return str(name), spec.id


def make_spec_graph(specs: Sequence[JobSpec], *, require_closed: bool = True) -> SpecGraph:
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
    graph = make_spec_graph(specs, require_closed=require_closed)
    final_specs = list(iter_downstream_specs(graph))
    for i, spec in enumerate(final_specs):
        spec.print(level=level, file=file, end=i == len(final_specs) - 1, style=style)


def format_spec_graph(
    specs: Sequence[JobSpec], *, style: str = "none", level: int = -1, require_closed: bool = True
) -> str:
    file = io.StringIO()
    print_spec_graph(specs, file=file, style=style, level=level, require_closed=require_closed)
    return file.getvalue()
