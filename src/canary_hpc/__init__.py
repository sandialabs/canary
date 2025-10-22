# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
from pathlib import Path

import canary
from _canary.plugins.subcommands.run import Run

from .argparsing import CanaryHPCBatchSpec
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


@canary.hookimpl
def canary_addoption(parser: "canary.Parser") -> None:
    CanaryHPCConductor.setup_legacy_parser(parser)


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
        CanaryHPCConductor.setup_parser(group)

        p = subparsers.add_parser("exec", help="Execute (run) the batch")
        CanaryHPCExecutor.setup_parser(p)

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
            conductor = CanaryHPCConductor(backend=scheduler)
            conductor.register(canary.config.pluginmanager)
            return conductor.run(args)
        elif args.hpc_cmd == "exec":
            # Batch is being executed within an allocation
            # register the CanaryHPCExector plugin so that executor.runtests is registered
            backend = args.canary_hpc_backend or canary.config.getoption("canary_hpc_scheduler")
            executor = CanaryHPCExecutor(
                backend=backend, batch=args.batch_id, case=args.canary_hpc_case
            )
            executor.register(canary.config.pluginmanager)
            return executor.run(args)
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
            print(str(location))
        elif args.batch_cmd == "log":
            location = self.location(args.batch_id)
            display_file(location / "canary-out.txt")
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

    def location(self, batch_id: str) -> Path:
        session = canary.Session(str(Path.cwd()), mode="r")
        root = Path(session.work_tree) / ".canary/canary_hpc/batches" / batch_id[:2]
        if root.exists() and (root / batch_id[2:]).exists():
            return root / batch_id[2:]
        elif matches := list(root.glob(f"{batch_id[2:]}*")):
            return matches[0]
        raise ValueError(f"Stage directory for batch {batch_id} not found in {session.work_tree}")

    def find_batches(self) -> list[str]:
        session = canary.Session(str(Path.cwd()), mode="r")
        root = Path(session.work_tree) / ".canary/canary_hpc/batches"
        batches: list[str] = []
        for p in root.iterdir():
            if p.is_dir():
                batches.extend(["".join([p.stem, c.stem]) for c in p.iterdir() if c.is_dir()])
        return batches

    def print_status(self, batch_id: str) -> None:
        location = self.location(batch_id)
        f = location / "index"
        case_ids = json.loads(f.read_text())
        session = canary.Session(str(Path.cwd()), mode="r")
        for case in session.cases:
            if case.id not in case_ids:
                case.mask = "[MASKED]"
        canary.config.options.report_chars = "A"
        canary.config.pluginmanager.hook.canary_statusreport(session=session)

    def describe(self, batch_id: str) -> None:
        print(f"Batch {batch_id}")
        location = self.location(batch_id)
        f = location / "index"
        case_ids = json.loads(f.read_text())
        session = canary.Session(str(Path.cwd()), mode="r")
        for case in session.cases:
            if case.id not in case_ids:
                continue
            if case.work_tree is None:
                case.work_tree = session.work_tree
            print(f"- name: {case.display_name}\n  location: {case.working_directory}")
        return


def display_file(file: Path) -> None:
    import pydoc

    print(f"{file}:")
    if not file.is_file():
        raise ValueError(f"{file}: no such file")
    pydoc.pager(file.read_text())
