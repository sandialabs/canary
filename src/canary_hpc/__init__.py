# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import glob
import json
import os
from typing import Sequence

import psutil

import canary
from _canary.plugins.subcommands.run import Run

from .argparsing import CanaryHPCBatchSpec
from .argparsing import CanaryHPCResourceSetter
from .argparsing import CanaryHPCSchedulerArgs
from .conductor import CanaryHPCConductor
from .executor import CanaryHPCExecutor

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_configure(config: "canary.Config") -> None:
    """Do some post configuration checks"""
    scheduler = config.getoption("canary_hpc_scheduler")
    command = config.getoption("command")
    if scheduler is not None and command == "run":
        # Run with the HPC.execute command
        config.ioptions.command = "hpc"
        config.options.command = "hpc"
        config.options.hpc_cmd = "run"
        if ival := getattr(config.ioptions, "canary_hpc_batchspec", None):
            # ioptions is the argparse.Namespace parsed from the command line, options is the
            # argparse.Namespace merged from the original invocation of canary.  They are only
            # different if this is a re-run scenario.  If the batchspec is defined in ioptions,
            # we use it (it was passed on the command line this invocation)
            setattr(config.options, "canary_hpc_batchspec", ival)
        else:
            # no batchspec was passed on the command line, so set the defaults
            setattr(config.options, "canary_hpc_batchspec", CanaryHPCBatchSpec.defaults())


class LegacyParserAdapter:
    def __init__(self, parser: "canary.Parser") -> None:
        self.parser = parser
        self.parser.add_argument(
            "-b",
            command=("run", "find"),
            group="canary hpc",
            metavar="option=value",
            action=CanaryHPCResourceSetter,
            help="Short cut for setting batch options.",
        )

    def add_argument(self, flag: str, *args, **kwargs):
        flag = "--hpc-" + flag[2:]
        self.parser.add_argument(flag, *args, command=("run", "find"), group="canary hpc", **kwargs)

    def parse_args(self, args: Sequence[str] | None = None) -> argparse.Namespace:
        return self.parser.parse_args(args)


@canary.hookimpl
def canary_addoption(parser: "canary.Parser") -> None:
    p = LegacyParserAdapter(parser)
    setup_parser(p)


def setup_parser(parser: canary.Parser | LegacyParserAdapter | argparse._ArgumentGroup) -> None:
    """Exists to accomodate ``canary hpc run`` and ``canary run -b ...``"""
    parser.add_argument(
        "--scheduler",
        dest="canary_hpc_scheduler",
        metavar="SCHEDULER",
        help="Submit batches to this HPC scheduler [alias: -b scheduler=SCHEDULER] [default: None]",
    )
    parser.add_argument(
        "--scheduler-args",
        dest="canary_hpc_scheduler_args",
        metavar="ARGS",
        action=CanaryHPCSchedulerArgs,
        help="Comma separated list of options to pass directly "
        "to the scheduler [alias: -b options=ARGS]",
    )
    parser.add_argument(
        "--batch-spec",
        dest="canary_hpc_batchspec",
        metavar="SPEC",
        action=CanaryHPCBatchSpec,
        help="Comma separated list of options to partition test cases into batches. "
        "See canary batch help --spec for help on batch specification syntax "
        "[alias: -b spec=SPEC]",
    )
    parser.add_argument(
        "--batch-workers",
        dest="canary_hpc_batch_workers",
        metavar="WORKERS",
        help="Run test cases in batches using WORKERS workers [alias: -b workers=WORKERS]",
    )
    parser.add_argument(
        "--batch-timeout-strategy",
        dest="canary_hpc_batch_timeout_strategy",
        metavar="STRATEGY",
        choices=("aggressive", "conservative"),
        help="Estimate batch runtime (queue time) conservatively or aggressively "
        "[alias: -b timeout=STRATEGY] [default: aggressive]",
    )


@canary.hookimpl
def canary_addcommand(parser: canary.Parser) -> None:
    parser.add_command(Batch())
    parser.add_command(HPC())


class HPC(canary.CanarySubcommand):
    name = "hpc"
    description = "Manage and run job batches on an HPC scheduler"

    def setup_parser(self, parser: canary.Parser):
        subparsers = parser.add_subparsers(dest="hpc_cmd", title="subcommands", metavar="")

        p = subparsers.add_parser("run", help="Batch test cases and submit to HPC scheduler")
        Run().setup_parser(p)
        group = p.add_argument_group(title="Batched execution options")
        setup_parser(group)

        p = subparsers.add_parser("exec", help="Execute (run) the batch")
        p.add_argument("--workers", type=int, help="Run tests in batch using this many workers")
        p.add_argument("--backend", dest="canary_hpc_backend", help="The HPC connect backend name")
        p.add_argument("--case", dest="canary_hpc_case", help="Run only this case")
        p.add_argument("batch_id")

        p = subparsers.add_parser("help", help="Additional canary_hpc help topics")
        p.add_argument(
            "--spec",
            default=False,
            action="store_true",
            help="Help on the batch specification syntax",
        )

    def execute(self, args: argparse.Namespace) -> int:
        if args.hpc_cmd == "run":
            scheduler = args.canary_hpc_scheduler
            if scheduler is None:
                raise ValueError("canary hpc run requires --scheduler")
            if n := args.canary_hpc_batch_workers:
                if n > psutil.cpu_count():
                    logger.warning(f"--hpc-batch-workers={n} > cpu_count={psutil.cpu_count()}")
            batchspec = args.canary_hpc_batchspec or CanaryHPCBatchSpec.defaults()
            CanaryHPCBatchSpec.validate_and_set_defaults(batchspec)
            setattr(canary.config.options, "canary_hpc_batchspec", batchspec)
            # Registering the conductor registers the canary_runtests implementation
            conductor = CanaryHPCConductor(backend=scheduler)
            canary.config.pluginmanager.register(conductor, f"canary_hpc{conductor.backend.name}")
            Run().execute(args)

        elif args.hpc_cmd == "exec":
            # Batch is being executed within an allocation
            # register the CanaryHPCExector plugin so that executor.runtests is registered
            backend = args.canary_hpc_backend or canary.config.getoption("canary_hpc_scheduler")
            executor = CanaryHPCExecutor(
                backend=backend, batch=args.batch_id, case=args.canary_hpc_case
            )
            executor.setup(config=canary.config._config)
            canary.config.pluginmanager.register(executor, f"canary_hpc{executor.backend.name}")
            n = len(executor.cases)
            logger.info(
                f"Selected {n} {canary.string.pluralize('test', n)} from batch {args.batch_id}"
            )
            case_specs = [f"/{case}" for case in executor.cases]
            session = canary.Session.casespecs_view(os.getcwd(), case_specs)
            session.run()
            canary.config.pluginmanager.hook.canary_runtests_summary(
                cases=session.active_cases(), include_pass=False, truncate=10
            )
        elif args.hpc_cmd == "help":
            self.extra_help(args)
        else:
            raise ValueError(f"canary hpc: unknown subcommand {args.hpc_cmd!r}")
        return 0

    def extra_help(self, args: argparse.Namespace) -> None:
        if args.spec:
            print(CanaryHPCBatchSpec.helppage())
        return


class Batch(canary.CanarySubcommand):
    name = "batch"
    description = "Manage and run job batches"

    def setup_parser(self, parser: canary.Parser):
        parser.epilog = self.in_session_note()
        subparsers = parser.add_subparsers(dest="batch_cmd", title="subcommands", metavar="")

        p = subparsers.add_parser("location", help="Print the location of the batch")
        p.add_argument("batch_id")

        p = subparsers.add_parser("log", help="Print the batch's log to the console")
        p.add_argument("batch_id")

        p = subparsers.add_parser("status", help="List statuses of each case in batch")
        p.add_argument("batch_id")

        subparsers.add_parser("list", help="List batch IDs")

        p = subparsers.add_parser("describe", help="Print each test case in batch")
        p.add_argument("batch_id")

    def execute(self, args: argparse.Namespace) -> int:
        if args.batch_cmd == "location":
            location = self.location(args.batch_id)
            print(location)
        elif args.batch_cmd == "log":
            location = self.location(args.batch_id)
            display_file(os.path.join(location, "canary-out.txt"))
        elif args.batch_cmd == "list":
            batches = self.find_batches()
            print("\n".join(batches))
        elif args.batch_cmd == "status":
            self.print_status(args.batch_id)
        elif args.batch_cmd == "describe":
            self.describe(args.batch_id)
        else:
            raise ValueError(f"canary batch: unknown subcommand {args.batch_cmd!r}")
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

    def describe(self, batch_id: str) -> None:
        print(f"Batch {batch_id}")
        location = self.location(batch_id)
        f = os.path.join(location, "index")
        with open(f, "r") as fh:
            case_ids = json.load(fh)
        session = canary.Session(os.getcwd(), mode="r")
        for case in session.cases:
            if case.id not in case_ids:
                continue
            if case.work_tree is None:
                case.work_tree = session.work_tree
            print(f"- name: {case.display_name}\n  location: {case.working_directory}")
        return


def display_file(file: str) -> None:
    import pydoc

    print(f"{file}:")
    if not os.path.isfile(file):
        raise ValueError(f"{file}: no such file")
    pydoc.pager(open(file).read())
