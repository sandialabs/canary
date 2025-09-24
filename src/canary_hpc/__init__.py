# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import glob
import json
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
def canary_resource_count_per_node(type: str) -> int | None:
    """determine if the resources for this test are satisfiable"""
    if props := canary.config.resource_pool.additional_properties.get("hpc_connect"):
        if count_per_node := props.get(f"{type}_per_node"):
            return count_per_node
    return None


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


@canary.hookimpl
def canary_subcommand() -> canary.CanarySubcommand:
    return Batch()


class Batch(canary.CanarySubcommand):
    name = "batch"
    description = "Get information about batch jobs"

    def setup_parser(self, parser: canary.Parser):
        parser.epilog = self.in_session_note()
        subparsers = parser.add_subparsers(dest="type", metavar="subcommands")
        p = subparsers.add_parser("location", help="Print the location of the batch")
        p.add_argument("batch_id")
        p = subparsers.add_parser("log", help="Print the batch's log to the console")
        p.add_argument("batch_id")
        p = subparsers.add_parser("status", help="List statuses of each case in batch")
        p.add_argument("batch_id")
        subparsers.add_parser("list", help="List batch IDs")

    def execute(self, args: argparse.Namespace) -> int:
        if args.type == "location":
            location = self.location(args.batch_id)
            print(location)
        elif args.type == "log":
            location = self.location(args.batch_id)
            display_file(os.path.join(location, "canary-out.txt"))
        elif args.type == "list":
            batches = self.find_batches()
            print("\n".join(batches))
        elif args.type == "status":
            self.print_status(args.batch_id)
        else:
            raise ValueError(f"canary batch: unknown batch subcommand {args.type!r}")
        return 0

    def location(self, batch_id: str) -> str:
        session = canary.Session(os.getcwd(), mode="r")
        root = os.path.join(session.work_tree, ".canary/batches", batch_id[:2])
        if os.path.exists(root) and os.path.exists(os.path.join(root, batch_id[2:])):
            return os.path.join(root, batch_id[2:])
        pattern = os.path.join(root, f"{batch_id[2:]}*")
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
        raise ValueError(f"Stage directory for batch {batch_id} not found in {session.work_tree}")

    def find_batches(self) -> list[str]:
        session = canary.Session(os.getcwd(), mode="r")
        root = os.path.join(session.work_tree, ".canary/batches")
        batches: list[str] = []
        for stem in os.listdir(root):
            leaves = os.listdir(os.path.join(root, stem))
            batches.extend([f"{stem}{leaf}" for leaf in leaves])
        return batches

    def print_status(self, batch_id: str) -> None:
        location = self.location(batch_id)
        f = os.path.join(location, "index")
        with open(f, "r") as fh:
            case_ids = json.load(fh)
        session = canary.Session(os.getcwd(), mode="r")
        for case in session.cases:
            if case.id not in case_ids:
                case.mask = "[MASKED]"
        canary.config.options.report_chars = "A"
        canary.config.pluginmanager.hook.canary_statusreport(session=session)


def display_file(file: str) -> None:
    import pydoc

    print(f"{file}:")
    if not os.path.isfile(file):
        raise ValueError(f"{file}: no such file")
    pydoc.pager(open(file).read())
