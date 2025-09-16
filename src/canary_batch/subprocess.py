from typing import Sequence

import hpc_connect
import psutil

import canary
from _canary.error import ResourceUnsatisfiableError

from . import runtests


class SubprocessBatchRunner:
    def __init__(self) -> None:
        self.nodes: int = 1
        self.backend = hpc_connect.get_backend("shell")
        self.cpus_per_node: int = psutil.cpu_count(logical=True)
        self.gpus_per_node: int = 0
        self.types: set[str] = {"cpus", "gpus"}
        self.slots_per_type: dict[str, int] = {
            "cpus": self.cpus_per_node,
            "gpus": self.gpus_per_node,
        }

    @canary.hookimpl
    def canary_resource_requirements_satisfiable(self, case: canary.TestCase) -> bool:
        """determine if the resources for this test are satisfiable"""
        required = case.required_resources()
        slots_reqd: dict[str, int] = {}
        for group in required:
            for item in group:
                if item["type"] not in self.types:
                    msg = f"required resource type {item['type']!r} is not available"
                    raise ResourceUnsatisfiableError(msg)
                slots_reqd[item["type"]] = slots_reqd.get(item["type"], 0) + item["slots"]
        for type, slots in slots_reqd.items():
            if self.slots_per_type[type] < slots:
                raise ResourceUnsatisfiableError(f"insufficient slots of {type!r} available")
        return True

    @canary.hookimpl(tryfirst=True)
    def canary_runtests(self, cases: Sequence[canary.TestCase], fail_fast: bool = False) -> int:
        return runtests.runtests(backend=self.backend, cases=cases, fail_fast=fail_fast)


@canary.hookimpl
def canary_batch_add_scheduler() -> dict[str, str | list[str]]:
    return {"name": "subprocess", "aliases": ["shell", "none"]}


@canary.hookimpl(trylast=True)
def canary_configure(config: canary.Config) -> None:
    if batchopts := config.getoption("batchopts"):
        if batchopts.get("scheduler") in ("shell", "subprocess", "none"):
            config.pluginmanager.register(SubprocessBatchRunner(), "canary_batchsubp")
