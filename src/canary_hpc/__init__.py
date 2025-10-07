# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import glob
import json
import os
from typing import Any

import psutil

import canary

from .batchopts import BatchResourceSetter
from .conductor import BatchConductor
from .executor import BatchExecutor

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_configure(config: "canary.Config") -> None:
    """Do some post configuration checks"""
    batchopts: dict[str, Any] = config.getoption("batchopts") or {}
    if not batchopts:
        return
    if execopts := batchopts.get("exec"):
        # Batch is being executed within an allocation
        hooks = BatchExecutor(
            backend=execopts["backend"], batch=execopts["batch"], case=execopts.get("case")
        )
        hooks.setup(config=config)
        config.pluginmanager.register(hooks, f"canary_hpc{hooks.backend.name}")
    elif backend := batchopts.get("backend"):
        if n := batchopts.get("workers"):
            if n > psutil.cpu_count():
                raise ValueError(f"-b workers={n} > cpu_count={psutil.cpu_count(logical=True)}")
        BatchResourceSetter.validate_and_set_defaults(batchopts)
        setattr(config.options, "batchopts", batchopts)
        hooks = BatchConductor(backend=backend)
        hooks.setup(config=config)
        config.pluginmanager.register(hooks, f"canary_hpc{hooks.backend.name}")
    else:
        raise ValueError("Missing required option -b backend=BACKEND")


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
