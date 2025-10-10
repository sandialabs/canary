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

from .argparsing import CanaryHPCBatchExec
from .argparsing import CanaryHPCBatchSpec
from .argparsing import CanaryHPCOption
from .argparsing import CanaryHPCResourceSetter
from .argparsing import CanaryHPCSchedulerArgs
from .conductor import CanaryHPCConductor
from .executor import CanaryHPCExecutor

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_configure(config: "canary.Config") -> None:
    """Do some post configuration checks"""
    opts: dict[str, Any] = config.getoption("canary_hpc") or {}
    if not opts:
        return
    if execopts := opts.get("batch_exec"):
        # Batch is being executed within an allocation
        hooks = CanaryHPCExecutor(
            backend=execopts["backend"], batch=execopts["batch"], case=execopts.get("case")
        )
        hooks.setup(config=config)
        config.pluginmanager.register(hooks, f"canary_hpc{hooks.backend.name}")
    elif scheduler := opts.get("scheduler"):
        if n := opts.get("batch_workers"):
            if n > psutil.cpu_count():
                raise ValueError(f"--hpc-batch-workers={n} > cpu_count={psutil.cpu_count()}")
        dest = CanaryHPCBatchSpec.p_dest
        iopts = getattr(canary.config.ioptions, "canary_hpc", {})
        if dest in iopts:
            # canary.config.set_main_options merges new options with old.  For the batch spec, we
            # don't want the merged result, so use the actual value passed on the command line
            opts[dest] = iopts[dest]
        else:
            # use the defaults, rather than risk using the merged result.
            opts[dest] = CanaryHPCBatchSpec.defaults()
        CanaryHPCBatchSpec.validate_and_set_defaults(opts)
        setattr(config.options, "canary_hpc", opts)
        hooks = CanaryHPCConductor(backend=scheduler)
        hooks.setup(config=config)
        config.pluginmanager.register(hooks, f"canary_hpc{hooks.backend.name}")
    else:
        raise ValueError("Missing required option -b backend=BACKEND")


@canary.hookimpl
def canary_addoption(parser: "canary.Parser") -> None:
    setup_parser(parser)


def setup_parser(parser: "canary.Parser") -> None:
    parser.add_argument(
        "-b",
        command=("run", "find"),
        group="canary hpc",
        metavar="option=value",
        action=CanaryHPCResourceSetter,
        help="Short cut for setting batch options.",
    )
    parser.add_argument(
        "--hpc-scheduler",
        dest="scheduler",
        command=("run", "find"),
        group="canary hpc",
        metavar="SCHEDULER",
        action=CanaryHPCOption,
        help="Submit batches to this HPC scheduler [alias: -b scheduler=SCHEDULER] [default: None]",
    )
    parser.add_argument(
        "--hpc-scheduler-args",
        dest=CanaryHPCSchedulerArgs.p_dest,
        command=("run", "find"),
        group="canary hpc",
        metavar="ARGS",
        action=CanaryHPCSchedulerArgs,
        help="Comma separated list of options to pass directly "
        "to the scheduler [alias: -b options=ARGS]",
    )
    parser.add_argument(
        "--hpc-batch-spec",
        dest=CanaryHPCBatchSpec.p_dest,
        command=("run", "find"),
        group="canary hpc",
        metavar="SPEC",
        action=CanaryHPCBatchSpec,
        help="Comma separated list of options to partition test cases into batches. "
        "See canary batch help --spec for help on batch specification syntax "
        "[alias: -b spec=SPEC]",
    )
    parser.add_argument(
        "--hpc-batch-workers",
        dest="batch_workers",
        command=("run", "find"),
        group="canary hpc",
        metavar="WORKERS",
        action=CanaryHPCOption,
        help="Run test cases in batches using WORKERS workers [alias: -b workers=WORKERS]",
    )
    parser.add_argument(
        "--hpc-batch-timeout-strategy",
        dest="batch_timeout_strategy",
        command=("run", "find"),
        group="canary hpc",
        metavar="STRATEGY",
        action=CanaryHPCOption,
        choices=("aggressive", "conservative"),
        help="Estimate batch runtime (queue time) conservatively or aggressively "
        "[alias: -b timeout=STRATEGY] [default: aggressive]",
    )
    parser.add_argument(
        "--hpc-batch-exec",
        dest=CanaryHPCBatchExec.p_dest,
        command=("run", "find"),
        group="canary hpc",
        metavar="SPEC",
        action=CanaryHPCBatchExec,
        help="Run the batch given by SPEC.  Note, this option is designed to be used internally "
        "by canary_hpc.CanaryHPCConductor to run batches [alias: -b exec=SPEC]",
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
        p = subparsers.add_parser("help", help="Additional canary_hpc help topics")
        p.add_argument(
            "--spec",
            default=False,
            action="store_true",
            help="Help on the batch specification syntax",
        )

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
        elif args.type == "help":
            self.extra_help(args)
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

    def extra_help(self, args: argparse.Namespace) -> None:
        if args.spec:
            print(CanaryHPCBatchSpec.helppage())
        return


def display_file(file: str) -> None:
    import pydoc

    print(f"{file}:")
    if not os.path.isfile(file):
        raise ValueError(f"{file}: no such file")
    pydoc.pager(open(file).read())
