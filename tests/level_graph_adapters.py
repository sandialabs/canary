# tests/test_level_graph_adapters.py

import dataclasses
from pathlib import Path
from typing import Sequence
from typing import cast

import pytest

from _canary.job import Job
from _canary.job_graph import make_job_graph
from _canary.job_graph import make_job_graph_from_levels
from _canary.jobspec import JobSpec
from _canary.jobspec import SpecDependency
from _canary.jobspec_graph import make_spec_graph
from _canary.jobspec_graph import make_spec_graph_from_levels


def graph_level_ids(graph) -> list[list[str]]:
    return [[item.id for item in level] for level in graph.levels]


def graph_topo_ids(graph) -> list[str]:
    return [item.id for item in graph.topo_order()]


def make_spec(spec_id: str, *deps: JobSpec) -> JobSpec:
    spec = JobSpec(
        file_root=Path("/unused"), file_path=Path(f"{spec_id}.pyt"), id=spec_id, family=spec_id
    )
    spec.dependencies.extend(SpecDependency(spec=dep, when="on_success") for dep in deps)
    return spec


@dataclasses.dataclass(eq=False)
class FakeJobDependency:
    job: "FakeJob"
    when: str = "on_success"


@dataclasses.dataclass(eq=False)
class FakeJob:
    id: str
    dependencies: list[FakeJobDependency] = dataclasses.field(default_factory=list)

    @property
    def name(self) -> str:
        return self.id

    @property
    def fullname(self) -> str:
        return self.id

    def display_name(self, **kwargs) -> str:
        return self.id


def make_job(job_id: str, *deps: FakeJob) -> FakeJob:
    job = FakeJob(id=job_id)
    job.dependencies.extend(FakeJobDependency(dep) for dep in deps)
    return job


def as_jobs(*jobs: FakeJob) -> Sequence[Job]:
    return cast(Sequence[Job], list(jobs))


def as_job_levels(levels: Sequence[Sequence[FakeJob]]) -> Sequence[Sequence[Job]]:
    return cast(Sequence[Sequence[Job]], levels)


# ---------------------------------------------------------------------------
# SpecGraph tests
# ---------------------------------------------------------------------------


def test_spec_graph_empty() -> None:
    graph = make_spec_graph([])

    assert len(graph) == 0
    assert graph_level_ids(graph) == []
    assert graph_topo_ids(graph) == []


def test_spec_graph_sorts_unordered_specs_into_levels() -> None:
    a = make_spec("a")
    b = make_spec("b")
    c = make_spec("c", a, b)
    d = make_spec("d", c)

    graph = make_spec_graph([d, c, b, a])

    assert graph_level_ids(graph) == [["a", "b"], ["c"], ["d"]]
    assert graph_topo_ids(graph) == ["a", "b", "c", "d"]


def test_spec_graph_exposes_dependencies_and_dependents() -> None:
    a = make_spec("a")
    b = make_spec("b")
    c = make_spec("c", a, b)
    d = make_spec("d", c)

    graph = make_spec_graph([d, c, b, a])

    assert [spec.id for spec in graph.dependencies_of("c")] == ["a", "b"]
    assert [spec.id for spec in graph.dependents_of("a")] == ["c"]
    assert [spec.id for spec in graph.dependents_of("b")] == ["c"]
    assert [spec.id for spec in graph.dependents_of("c")] == ["d"]


def test_spec_graph_from_levels_preserves_given_level_order() -> None:
    a = make_spec("a")
    b = make_spec("b")
    c = make_spec("c", a, b)
    d = make_spec("d", c)

    graph = make_spec_graph_from_levels([[b, a], [c], [d]])

    assert graph_level_ids(graph) == [["b", "a"], ["c"], ["d"]]
    assert graph_topo_ids(graph) == ["b", "a", "c", "d"]


def test_spec_graph_from_levels_rejects_invalid_level_order() -> None:
    a = make_spec("a")
    b = make_spec("b")
    c = make_spec("c", a, b)
    d = make_spec("d", c)

    with pytest.raises(ValueError):
        make_spec_graph_from_levels([[c, a, b], [d]])


def test_spec_graph_rejects_duplicate_ids() -> None:
    a1 = make_spec("a")
    a2 = make_spec("a")

    with pytest.raises(ValueError):
        make_spec_graph([a1, a2])


def test_spec_graph_rejects_missing_dependency_by_default() -> None:
    missing = make_spec("missing")
    c = make_spec("c", missing)

    with pytest.raises(ValueError):
        make_spec_graph([c])


def test_spec_graph_can_ignore_missing_dependency_when_not_closed() -> None:
    missing = make_spec("missing")
    c = make_spec("c", missing)

    graph = make_spec_graph([c], require_closed=False)

    assert graph_level_ids(graph) == [["c"]]
    assert graph_topo_ids(graph) == ["c"]


def test_spec_graph_detects_cycle() -> None:
    a = make_spec("a")
    b = make_spec("b", a)
    a.dependencies.append(SpecDependency(spec=b, when="on_success"))

    with pytest.raises(ValueError):
        make_spec_graph([a, b])


# ---------------------------------------------------------------------------
# JobGraph tests
# ---------------------------------------------------------------------------


def test_job_graph_empty() -> None:
    graph = make_job_graph([])

    assert len(graph) == 0
    assert graph_level_ids(graph) == []
    assert graph_topo_ids(graph) == []


def test_job_graph_sorts_unordered_jobs_into_levels() -> None:
    a = make_job("a")
    b = make_job("b")
    c = make_job("c", a, b)
    d = make_job("d", c)

    graph = make_job_graph(as_jobs(d, c, b, a))

    assert graph_level_ids(graph) == [["a", "b"], ["c"], ["d"]]
    assert graph_topo_ids(graph) == ["a", "b", "c", "d"]


def test_job_graph_exposes_dependencies_and_dependents() -> None:
    a = make_job("a")
    b = make_job("b")
    c = make_job("c", a, b)
    d = make_job("d", c)

    graph = make_job_graph(as_jobs(d, c, b, a))

    assert [job.id for job in graph.dependencies_of("c")] == ["a", "b"]
    assert [job.id for job in graph.dependents_of("a")] == ["c"]
    assert [job.id for job in graph.dependents_of("b")] == ["c"]
    assert [job.id for job in graph.dependents_of("c")] == ["d"]


def test_job_graph_from_levels_preserves_given_level_order() -> None:
    a = make_job("a")
    b = make_job("b")
    c = make_job("c", a, b)
    d = make_job("d", c)

    graph = make_job_graph_from_levels(as_job_levels([[b, a], [c], [d]]))

    assert graph_level_ids(graph) == [["b", "a"], ["c"], ["d"]]
    assert graph_topo_ids(graph) == ["b", "a", "c", "d"]


def test_job_graph_from_levels_rejects_invalid_level_order() -> None:
    a = make_job("a")
    b = make_job("b")
    c = make_job("c", a, b)
    d = make_job("d", c)

    with pytest.raises(ValueError):
        make_job_graph_from_levels(as_job_levels([[c, a, b], [d]]))


def test_job_graph_rejects_duplicate_ids() -> None:
    a1 = make_job("a")
    a2 = make_job("a")

    with pytest.raises(ValueError):
        make_job_graph(as_jobs(a1, a2))


def test_job_graph_rejects_missing_dependency_by_default() -> None:
    missing = make_job("missing")
    c = make_job("c", missing)

    with pytest.raises(ValueError):
        make_job_graph(as_jobs(c))


def test_job_graph_can_ignore_missing_dependency_when_not_closed() -> None:
    missing = make_job("missing")
    c = make_job("c", missing)

    graph = make_job_graph(as_jobs(c), require_closed=False)

    assert graph_level_ids(graph) == [["c"]]
    assert graph_topo_ids(graph) == ["c"]


def test_job_graph_detects_cycle() -> None:
    a = make_job("a")
    b = make_job("b", a)
    a.dependencies.append(FakeJobDependency(job=b))

    with pytest.raises(ValueError):
        make_job_graph(as_jobs(a, b))
