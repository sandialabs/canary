from typing import Any
from typing import Sequence

import hpc_connect

import canary
from _canary.error import ResourceUnsatisfiableError

from . import runtests


class SchedulerHooks:
    def __init__(self, name: str) -> None:
        self.backend = hpc_connect.get_backend(name)

    @canary.hookimpl
    def canary_resource_requirements_satisfiable(self, case: canary.TestCase) -> bool:
        """determine if the resources for this test are satisfiable"""
        required = case.required_resources()
        slots_reqd: dict[str, int] = {}
        count_per_node: dict[str, int] = {}
        for group in required:
            for item in group:
                type: str = item["type"]
                try:
                    count_per_node.setdefault(type, self.backend.config.count_per_node(type))
                except ValueError:
                    msg = f"required resource type {type!r} is not available"
                    raise ResourceUnsatisfiableError(msg) from None
                slots_reqd[type] = slots_reqd.get(type, 0) + item["slots"]
        n: int = self.backend.config.node_count
        slots_per_type: dict[str, int] = {t: n * cpn for t, cpn in count_per_node.items()}
        for type, slots in slots_reqd.items():
            if slots_per_type[type] < slots:
                raise ResourceUnsatisfiableError(f"insufficient slots of {type!r} available")
        return True

    @canary.hookimpl(tryfirst=True)
    def canary_runtests(self, cases: Sequence[canary.TestCase]) -> int:
        return runtests.runtests(backend=self.backend, cases=cases)


@canary.hookimpl(specname="canary_batch_add_scheduler")
def add_subprocess_scheduler() -> dict[str, str | list[str]]:
    return {"name": "subprocess", "aliases": ["shell", "none"]}


@canary.hookimpl(specname="canary_batch_get_scheduler")
def get_subprocess_scheduler(scheduler: str) -> Any:
    if scheduler in ("shell", "subprocess", "none"):
        return SchedulerHooks("shell")
    return None


@canary.hookimpl(specname="canary_batch_add_scheduler")
def add_slurm_scheduler() -> dict[str, str | list[str]]:
    return {"name": "slurm", "aliases": ["sbatch"]}


@canary.hookimpl(specname="canary_batch_get_scheduler")
def get_slurm_scheduler(scheduler: str) -> Any:
    if scheduler in ("slurm", "sbatch"):
        return SchedulerHooks("slurm")
    return None


@canary.hookimpl(specname="canary_batch_add_scheduler")
def add_pbs_scheduler() -> dict[str, str | list[str]]:
    return {"name": "pbs", "aliases": ["qsub"]}


@canary.hookimpl(specname="canary_batch_get_scheduler")
def get_pbs_scheduler(scheduler: str) -> Any:
    if scheduler in ("pbs", "qsub"):
        return SchedulerHooks("pbs")
    return None


@canary.hookimpl(specname="canary_batch_add_scheduler")
def add_flux_scheduler() -> dict[str, str | list[str]]:
    return {"name": "flux"}


@canary.hookimpl(specname="canary_batch_get_scheduler")
def get_flux_scheduler(scheduler: str) -> Any:
    if scheduler in ("flux",):
        return SchedulerHooks("flux")
    return None
