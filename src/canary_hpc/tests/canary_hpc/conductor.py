# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
from typing import Any

import pytest

from canary_hpc.conductor import create_batch_specs


class FakeBackend:
    def __init__(self, counts: dict[str, int], failures: set[str] | None = None) -> None:
        self.counts = dict(counts)
        self.failures = set(failures or ())
        self.name = "fake"

    def count_per_node(self, rtype: str) -> int:
        if rtype in self.failures:
            raise ValueError(f"{rtype} unavailable")
        if rtype not in self.counts:
            raise ValueError(f"{rtype} unavailable")
        return self.counts[rtype]


class FakeResourceManager:
    def __init__(self, types: list[str]) -> None:
        self._types = list(types)

    def types(self) -> list[str]:
        return list(self._types)


@dataclasses.dataclass
class FakeNodeRequest:
    resources: list[dict[str, Any]]
    exclusive: bool = False


@dataclasses.dataclass
class FakeDependency:
    job: "FakeJob"
    when: str | None = "on_success"


class FakeWorkspace:
    session: str | None = "fake-session"


@dataclasses.dataclass
class FakeJob:
    id: str
    cpus: int = 1
    gpus: int = 0
    runtime: float = 10.0
    dependencies: list[FakeDependency] = dataclasses.field(default_factory=list)
    node_count: int = 1

    workspace: FakeWorkspace = dataclasses.field(default_factory=FakeWorkspace)

    def required_resources(self):
        requests = []

        for _ in range(self.node_count):
            resources = []
            for _ in range(self.cpus):
                resources.append({"type": "cpus", "slots": 1})
            for _ in range(self.gpus):
                resources.append({"type": "gpus", "slots": 1})
            requests.append(FakeNodeRequest(resources=resources))

        return requests

    def cost(self) -> float:
        return (self.cpus**2 + self.runtime**2) ** 0.5

    @property
    def fullname(self) -> str:
        return self.id

    @property
    def name(self) -> str:
        return self.id


def fake_conductor(*, counts: dict[str, int], failures: set[str] | None = None):
    from canary_hpc.conductor import CanaryHPCConductor

    conductor = CanaryHPCConductor.__new__(CanaryHPCConductor)
    conductor.backend = FakeBackend(counts=counts, failures=failures)
    return conductor


def batchspec(
    *,
    layout: str = "flat",
    nodes: str = "same",
    count: int | str | None = None,
    duration: float | None = 600.0,
) -> dict[str, object]:
    return {"layout": layout, "nodes": nodes, "count": count, "duration": duration}


def all_batch_job_ids(specs) -> set[str]:
    return {job.id for spec in specs for job in spec.jobs}


def test_create_batch_specs_passes_resource_capacity_metadata_flat_nodes_same() -> None:
    jobs = [
        FakeJob("a", cpus=2, runtime=10.0, node_count=1),
        FakeJob("b", cpus=4, runtime=10.0, node_count=1),
    ]

    specs = create_batch_specs(
        jobs=jobs,  # type: ignore[arg-type]
        batchspec=batchspec(layout="flat", nodes="same", duration=600.0),
        cpus_per_node=8,
        workers=2,
    )

    assert specs
    assert all_batch_job_ids(specs) == {"a", "b"}

    for spec in specs:
        assert spec.estimated_runtime is not None
        assert spec.schedule_metadata["width"] == 8
        assert spec.schedule_metadata["workers"] == 2
        assert spec.schedule_metadata["node_count"] == 1
        assert spec.schedule_metadata["resource_capacity"]["cpus"] == 8


def test_create_batch_specs_partitions_flat_nodes_same_by_node_count() -> None:
    jobs = [
        FakeJob("one_node", cpus=2, runtime=10.0, node_count=1),
        FakeJob("two_node", cpus=2, runtime=10.0, node_count=2),
    ]

    specs = create_batch_specs(
        jobs=jobs,  # type: ignore[arg-type]
        batchspec=batchspec(layout="flat", nodes="same", duration=600.0),
        cpus_per_node=8,
        workers=None,
    )

    assert specs
    assert all_batch_job_ids(specs) == {"one_node", "two_node"}

    widths_by_job = {}
    for spec in specs:
        for job in spec.jobs:
            widths_by_job[job.id] = spec.schedule_metadata["width"]

    assert widths_by_job["one_node"] == 8
    assert widths_by_job["two_node"] == 16


def test_create_batch_specs_sets_cross_partition_dependencies() -> None:
    a = FakeJob("a", cpus=1, runtime=10.0, node_count=1)
    b = FakeJob("b", cpus=1, runtime=10.0, node_count=2)
    b.dependencies.append(FakeDependency(job=a))

    specs = create_batch_specs(
        jobs=[a, b],  # type: ignore[list-item]
        batchspec=batchspec(layout="flat", nodes="same", duration=600.0),
        cpus_per_node=8,
        workers=None,
    )

    assert all_batch_job_ids(specs) == {"a", "b"}

    spec_by_job = {}
    for spec in specs:
        for job in spec.jobs:
            spec_by_job[job.id] = spec

    assert spec_by_job["a"] in spec_by_job["b"].dependencies


def test_create_batch_specs_allocates_global_count_across_partitions() -> None:
    # This dependency creates two topological levels, so flat layout needs at
    # least two partitions/counts.
    a = FakeJob("a", cpus=1, runtime=10.0)
    b = FakeJob("b", cpus=1, runtime=10.0)
    b.dependencies.append(FakeDependency(job=a))

    specs = create_batch_specs(
        jobs=[a, b],  # type: ignore[list-item]
        batchspec=batchspec(layout="flat", nodes="any", count=2, duration=None),
        cpus_per_node=8,
        workers=None,
    )

    assert len(specs) == 2
    assert all_batch_job_ids(specs) == {"a", "b"}


def test_create_batch_specs_rejects_insufficient_count_for_flat_partitions() -> None:
    # count=1 with dependent jobs used to raise; now it produces one batch.
    # count >= 2 but < nparts (i.e. count=1 is now valid; this test verifies
    # that count >= 2 is still required when there are more than 2 DAG levels).
    a = FakeJob("a", cpus=1, runtime=10.0)
    b = FakeJob("b", cpus=1, runtime=10.0)
    c = FakeJob("c", cpus=1, runtime=10.0)
    b.dependencies.append(FakeDependency(job=a))
    c.dependencies.append(FakeDependency(job=b))
    # 3 topological levels: a → b → c.  count=2 < 3 partitions → must raise.
    with pytest.raises(ValueError, match="insufficient"):
        create_batch_specs(
            jobs=[a, b, c],  # type: ignore[list-item]
            batchspec=batchspec(layout="flat", nodes="any", count=2, duration=None),
            cpus_per_node=8,
            workers=None,
        )


def test_create_batch_specs_atomic_defaults_to_component_batches_when_count_max() -> None:
    a = FakeJob("a", cpus=1, runtime=10.0)
    b = FakeJob("b", cpus=1, runtime=10.0)
    c = FakeJob("c", cpus=1, runtime=10.0)
    b.dependencies.append(FakeDependency(job=a))

    specs = create_batch_specs(
        jobs=[a, b, c],  # type: ignore[list-item]
        batchspec=batchspec(layout="atomic", nodes="any", count="max", duration=None),
        cpus_per_node=8,
        workers=None,
    )

    assert len(specs) == 2
    batch_sets = {frozenset(job.id for job in spec.jobs) for spec in specs}
    assert batch_sets == {frozenset({"a", "b"}), frozenset({"c"})}

    # Atomic batches should not have cross-batch dependencies.
    assert all(not spec.dependencies for spec in specs)


def test_create_batch_specs_rejects_atomic_nodes_same() -> None:
    jobs = [FakeJob("a")]

    with pytest.raises(ValueError, match="layout=atomic requires nodes=any"):
        create_batch_specs(
            jobs=jobs,  # type: ignore[arg-type]
            batchspec=batchspec(layout="atomic", nodes="same", count="max", duration=None),
            cpus_per_node=8,
            workers=None,
        )


def test_create_batch_specs_rejects_count_for_flat_nodes_same_mixed_node_counts() -> None:
    # Explicitly pairing count with nodes=same on a mixed-node-count suite is
    # an error.  The improved message tells the user to use nodes:any instead.
    jobs = [
        FakeJob("one_node", cpus=2, runtime=10.0, node_count=1),
        FakeJob("two_node", cpus=2, runtime=10.0, node_count=2),
    ]

    with pytest.raises(ValueError, match="nodes=any"):
        create_batch_specs(
            jobs=jobs,  # type: ignore[arg-type]
            batchspec=batchspec(layout="flat", nodes="same", count=2, duration=None),
            cpus_per_node=8,
            workers=None,
        )


def test_create_batch_specs_count_without_explicit_nodes_uses_nodes_any() -> None:
    # When count is given without an explicit nodes= value, with_defaults()
    # picks nodes=any, so a mixed-node-count suite is batched into a single
    # pool and count is honoured as a global budget.
    jobs = [
        FakeJob("j1", cpus=2, runtime=10.0, node_count=1),
        FakeJob("j2", cpus=2, runtime=10.0, node_count=1),
        FakeJob("j3", cpus=4, runtime=10.0, node_count=8),
        FakeJob("j4", cpus=4, runtime=10.0, node_count=8),
    ]

    from canary_hpc.batching import BatchingSpec

    # Simulate what the CLI produces: count given, nodes not specified
    default_spec = BatchingSpec.with_defaults(count=1)
    assert default_spec.node_policy == "any"

    specs = create_batch_specs(
        jobs=jobs,  # type: ignore[arg-type]
        batchspec=default_spec,
        cpus_per_node=8,
        workers=None,
    )

    assert specs
    assert all_batch_job_ids(specs) == {"j1", "j2", "j3", "j4"}
    # count=1 is honoured: one batch containing all four jobs
    assert len(specs) == 1


def test_create_batch_specs_count_1_with_dependent_jobs_produces_single_batch() -> None:
    # Regression test for: count=1 with a suite containing dependent jobs
    # (multiple DAG partitions) previously raised
    #   ValueError: count=1 is insufficient for 2 DAG/resource partitions
    # The fix: count=1 is an atomic single-batch request; DAG partitioning is
    # skipped and all jobs land in one Slurm submission.
    base = FakeJob("base", cpus=2, runtime=30.0)
    aggregate = FakeJob("agg", cpus=1, runtime=5.0, dependencies=[FakeDependency(job=base)])

    from canary_hpc.batching import BatchingSpec

    spec = BatchingSpec.with_defaults(count=1)

    specs = create_batch_specs(
        jobs=[base, aggregate],  # type: ignore[arg-type]
        batchspec=spec,
        cpus_per_node=8,
        workers=None,
    )

    assert len(specs) == 1
    assert all_batch_job_ids(specs) == {"base", "agg"}


def test_create_batch_specs_allows_count_for_flat_nodes_same_single_node_count() -> None:
    jobs = [
        FakeJob("a", cpus=2, runtime=10.0, node_count=1),
        FakeJob("b", cpus=2, runtime=10.0, node_count=1),
        FakeJob("c", cpus=2, runtime=10.0, node_count=1),
    ]

    specs = create_batch_specs(
        jobs=jobs,  # type: ignore[arg-type]
        batchspec=batchspec(layout="flat", nodes="same", count=2, duration=None),
        cpus_per_node=8,
        workers=None,
    )

    assert specs
    assert all_batch_job_ids(specs) == {"a", "b", "c"}
    assert len(specs) <= 2


def test_create_batch_specs_allows_max_count_for_flat_nodes_same_mixed_node_counts() -> None:
    # MAX_COUNT ("max") means "as many batches as possible" and is well-defined
    # even across mixed node counts, so it must not be rejected.
    jobs = [
        FakeJob("one_node", cpus=2, runtime=10.0, node_count=1),
        FakeJob("two_node", cpus=2, runtime=10.0, node_count=2),
    ]

    specs = create_batch_specs(
        jobs=jobs,  # type: ignore[arg-type]
        batchspec=batchspec(layout="flat", nodes="same", count="max", duration=None),
        cpus_per_node=8,
        workers=None,
    )

    assert specs
    assert all_batch_job_ids(specs) == {"one_node", "two_node"}


def test_create_batch_specs_gpu_capacity_appears_in_metadata() -> None:
    jobs = [
        FakeJob("gpu_a", cpus=2, gpus=1, runtime=10.0),
        FakeJob("cpu_b", cpus=4, gpus=0, runtime=10.0),
    ]

    specs = create_batch_specs(
        jobs=jobs,  # type: ignore[arg-type]
        batchspec=batchspec(layout="flat", nodes="any", duration=600.0),
        cpus_per_node=8,
        workers=None,
    )

    assert specs
    assert all_batch_job_ids(specs) == {"gpu_a", "cpu_b"}

    capacities = [spec.schedule_metadata["resource_capacity"] for spec in specs]

    assert any(capacity.get("gpus") == 1 for capacity in capacities)
    assert all(capacity["cpus"] == 8 for capacity in capacities)


def test_create_batch_specs_uses_resources_per_node_for_capacity() -> None:
    jobs = [
        FakeJob("gpu_a", cpus=2, gpus=1, runtime=10.0),
        FakeJob("gpu_b", cpus=2, gpus=1, runtime=10.0),
    ]

    specs = create_batch_specs(
        jobs=jobs,  # type: ignore[arg-type]
        batchspec=batchspec(layout="flat", nodes="any", duration=600.0),
        cpus_per_node=8,
        workers=None,
        resources_per_node={"cpus": 8, "gpus": 4},
    )

    assert specs
    assert all_batch_job_ids(specs) == {"gpu_a", "gpu_b"}

    for spec in specs:
        assert spec.schedule_metadata["resource_capacity"]["cpus"] == 8
        assert spec.schedule_metadata["resource_capacity"]["gpus"] == 4


def test_backend_resources_per_node_collects_homogeneous_resources(monkeypatch) -> None:
    import canary

    conductor = fake_conductor(counts={"cpus": 64, "gpus": 4, "frombulators": 2})

    monkeypatch.setattr(
        canary.config, "resource_manager", FakeResourceManager(["cpus", "gpus", "frombulators"])
    )

    resources = conductor.backend_resources_per_node()

    assert resources == {"cpus": 64, "gpus": 4, "frombulators": 2}


def test_backend_resources_per_node_skips_unavailable_non_cpu_resources(monkeypatch) -> None:
    import canary

    conductor = fake_conductor(counts={"cpus": 64, "gpus": 4}, failures={"frombulators"})

    monkeypatch.setattr(
        canary.config, "resource_manager", FakeResourceManager(["cpus", "gpus", "frombulators"])
    )

    resources = conductor.backend_resources_per_node()

    assert resources == {"cpus": 64, "gpus": 4}


def test_backend_resources_per_node_requires_cpus(monkeypatch) -> None:
    import canary

    conductor = fake_conductor(counts={"gpus": 4})

    monkeypatch.setattr(canary.config, "resource_manager", FakeResourceManager(["cpus", "gpus"]))

    with pytest.raises(ValueError, match="Could not determine 'cpus' count per node"):
        conductor.backend_resources_per_node()


def test_backend_resources_per_node_uses_singular_plural_fallback(monkeypatch) -> None:
    import canary

    conductor = fake_conductor(counts={"cpu": 32, "gpu": 2})

    monkeypatch.setattr(canary.config, "resource_manager", FakeResourceManager(["cpus", "gpus"]))

    resources = conductor.backend_resources_per_node()

    assert resources == {"cpus": 32, "gpus": 2}


def test_create_batch_specs_exact_final_estimate_metadata() -> None:
    jobs = [FakeJob("a", cpus=1, runtime=10.0), FakeJob("b", cpus=1, runtime=10.0)]

    specs = create_batch_specs(
        jobs=jobs,  # type: ignore[arg-type]
        batchspec=batchspec(layout="flat", nodes="any", count=1, duration=None),
        cpus_per_node=8,
        workers=None,
        resources_per_node={"cpus": 8},
        exact_final_estimate=True,
    )

    assert len(specs) == 1
    assert specs[0].schedule_metadata["exact_final_estimate"] is True
    assert specs[0].schedule_metadata["simulated_runtime"] is not None
