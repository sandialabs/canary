# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from typing import Any
from typing import Generator

import psutil

import canary

from . import schedulers
from .batchopts import BatchResourceSetter
from .testbatch import TestBatch

logger = canary.get_logger(__name__)


class BatchHooks:
    @canary.hookspec
    def canary_hpc_add_scheduler(self) -> dict[str, str | list[str]]:  # type: ignore[empty-body]
        """Add the name of a recognized scheduler

        Returns
        -------
           info: dict
             info['name'] (required) is the name of the scheduler
             info['aliases'] (optional) is a list of aliases

        """

    @canary.hookspec(firstresult=True)
    def canary_hpc_get_scheduler(self, scheduler: str) -> Any:  # type: ignore[empty-body]
        ...


@canary.hookimpl
def canary_addhooks(pluginmanager: "canary.CanaryPluginManager") -> None:
    pluginmanager.add_hookspecs(BatchHooks)
    pluginmanager.register(schedulers)


@canary.hookimpl(wrapper=True)
def canary_hpc_add_scheduler() -> Generator[None, list[dict[str, str | list[str]]], list[str]]:
    schedulers: set[str] = set()
    res = yield
    for info in res:
        schedulers.add(info["name"])  # type: ignore
        if aliases := info.get("aliases"):
            schedulers.update(aliases)  # type: ignore
    return list(schedulers)


@canary.hookimpl
def canary_configure(config: "canary.Config") -> None:
    """Do some post configuration checks"""
    batchopts: dict[str, Any] = config.getoption("batchopts")
    if batchopts:
        scheduler = batchopts.pop("scheduler", None)
        if scheduler == "null":
            batchopts.clear()
        elif scheduler is None:
            raise ValueError("Test batching requires a batchopts:scheduler")
        else:
            schedulers = config.pluginmanager.hook.canary_hpc_add_scheduler()
            if scheduler not in schedulers:
                raise ValueError(
                    f"Unknown scheduler {scheduler!r}, choose from {', '.join(schedulers)}"
                )
            batchopts["scheduler"] = scheduler
        if n := batchopts.get("workers"):
            if n > psutil.cpu_count():
                raise ValueError(f"-b workers={n} > cpu_count={psutil.cpu_count(logical=True)}")
        setattr(config.options, "batchopts", batchopts)
        if batchopts:
            BatchResourceSetter.validate_and_set_defaults(batchopts)
            sched = canary.config.pluginmanager.hook.canary_hpc_get_scheduler(scheduler=scheduler)
            canary.config.pluginmanager.register(sched, f"canary_hpc{sched.backend.name}")
            cfgset = lambda t, v: canary.config.set(f"machine:{t}", v, scope="defaults")
            cfgset("node_count", sched.backend.config.node_count)
            cfgset("gpus_per_node", sched.backend.config.gpus_per_node)
            cfgset("cpus_per_node", sched.backend.config.cpus_per_node)


@canary.hookimpl
def canary_runtests_startup(args: argparse.Namespace) -> None:
    if batch_id := getattr(args, "batch_id", None):
        if "CANARY_BATCH_ID" not in os.environ:
            os.environ["CANARY_BATCH_ID"] = str(batch_id)
        elif not batch_id == os.environ["CANARY_BATCH_ID"]:
            raise ValueError("env batch id inconsistent with cli batch id")
        args.mode = "a"
        case_ids = TestBatch.loadindex(batch_id)
        if case_ids is None:
            raise ValueError(f"could not load case ids for batch {batch_id!r}")
        n = len(case_ids)
        logger.info(f"Selected {n} {canary.string.pluralize('test', n)} from batch {batch_id}")
        setattr(args, "case_specs", [f"/{_}" for _ in case_ids])


@canary.hookimpl
def canary_addoption(parser: "canary.Parser") -> None:
    parser.add_argument(
        "-b",
        action=BatchResourceSetter,
        metavar="resource",
        command=("run", "find"),
        group="batch control",
        dest="batchopts",
        help=BatchResourceSetter.help_page("-b"),
    )
    parser.add_argument("--batch-id", command="run", group="batch control", help="Run this batch")
