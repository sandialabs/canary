# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import multiprocessing as mp
import threading
from collections import Counter
from pathlib import Path
from typing import Any
from typing import Sequence

import hpc_connect

import canary
from _canary.plugins.subcommands.run import Run
from _canary.queue_executor import ResourceQueueExecutor
from _canary.resource_pool import ResourcePool
from _canary.resource_pool.rpool import Outcome
from _canary.runtest import Runner
from _canary.testexec import ExecutionSpace
from _canary.third_party.color import colorize
from _canary.util import cpu_count

from .argparsing import CanaryHPCBatchSpec
from .argparsing import CanaryHPCResourceSetter
from .argparsing import CanaryHPCSchedulerArgs
from .batching import batch_testcases
from .batchspec import BatchSpec
from .batchspec import TestBatch
from .queue import ResourceQueue

global_lock = threading.Lock()
logger = canary.get_logger(__name__)


class CanaryHPCConductor:
    def __init__(self, *, backend: str) -> None:
        self.backend: hpc_connect.HPCSubmissionManager = hpc_connect.get_backend(backend)
        # compute the total slots per resource type so that we can determine whether a test can be
        # run by this backend.
        self._slots_per_resource_type: Counter[str] | None = None
        rtypes: set[str] = {"cpus", "gpus"}
        for rtype in self.backend.config.resource_types():
            # canary resource pool uses the plural, whereas the hpc-connect resource set uses
            # the singular
            rtype = rtype if rtype.endswith("s") else f"{rtype}s"
            rtypes.add(rtype)
        self.available_resource_types = sorted(rtypes)

        # The batch conductor resource pool is used for checking in/out resources to run the
        # _batches_, which amounts to submitting the batch to the scheduler and waiting for the job
        # to finish.  Batches have no specialized resource requirements, just need cpus to run the
        # submission on.
        self.rpool = ResourcePool()
        self.rpool.populate(cpus=cpu_count())

    def register(self, pluginmanager: canary.CanaryPluginManager) -> None:
        pluginmanager.register(self, "canary_hpc_conductor")

    def run(self, args: argparse.Namespace) -> int:
        if n := args.canary_hpc_batch_workers:
            if n > cpu_count():
                logger.warning(f"--hpc-batch-workers={n} > cpu_count={cpu_count()}")
        batchspec = args.canary_hpc_batchspec or CanaryHPCBatchSpec.defaults()
        CanaryHPCBatchSpec.validate_and_set_defaults(batchspec)
        setattr(canary.config.options, "canary_hpc_batchspec", batchspec)
        return Run().execute(args)

    @property
    def slots_per_resource_type(self) -> Counter[str]:
        if self._slots_per_resource_type is None:
            self._slots_per_resource_type = Counter()
            node_count = self.backend.config.node_count
            slots_per_type: int = 1
            for type in self.backend.config.resource_types():
                count = self.backend.config.count_per_node(type)
                if not type.endswith("s"):
                    type += "s"
                self._slots_per_resource_type[type] = slots_per_type * count * node_count
        assert self._slots_per_resource_type is not None
        return self._slots_per_resource_type

    @canary.hookimpl
    def canary_resource_pool_count(self, type: str) -> int:
        node_count = self.backend.config.node_count
        if type in ("nodes", "node"):
            return node_count
        try:
            type_per_node = self.backend.config.count_per_node(type)
        except ValueError:
            return 0
        else:
            return node_count * type_per_node

    @canary.hookimpl
    def canary_resource_pool_types(self) -> list[str]:
        return self.available_resource_types

    @canary.hookimpl
    def canary_resource_pool_accommodates(self, case: canary.TestCase) -> Outcome:
        return self.backend_accommodates(case)

    def backend_accommodates(self, case: canary.TestCase) -> Outcome:
        """determine if the resources for this test are available"""

        slots_needed: Counter[str] = Counter()
        missing: set[str] = set()

        # Step 1: Gather resource requirements and detect missing types
        for member in case.required_resources():
            rtype = member["type"]
            if rtype in self.slots_per_resource_type:
                slots_needed[rtype] += member["slots"]
            else:
                missing.add(rtype)
        if missing:
            types = colorize("@*{%s}" % ",".join(sorted(missing)))
            key = canary.string.pluralize("Resource", n=len(missing))
            return Outcome(False, reason=f"{key} unavailable: {types}")

        # Step 2: Check available slots vs. needed slots
        wanting: dict[str, tuple[int, int]] = {}
        for rtype, slots in slots_needed.items():
            slots_avail = self.slots_per_resource_type[rtype]
            if slots_avail < slots:
                wanting[rtype] = (slots, slots_avail)
        if wanting:
            reason: str
            if canary.config.get("debug"):
                fmt = lambda t, n, m: "@*{%s} (requested %d, available %d)" % (colorize(t), n, m)
                types = ", ".join(fmt(k, *wanting[k]) for k in sorted(wanting))
                reason = f"{case}: insufficient slots of {types}"
            else:
                types = ", ".join(colorize("@*{%s}" % t) for t in wanting)
                reason = f"insufficient slots of {types}"
            return Outcome(False, reason=reason)

        # Step 3: all good
        return Outcome(True)

    @canary.hookimpl(tryfirst=True)
    def canary_runtests(self, runner: "Runner") -> bool:
        """Run each test case in ``cases``.

        Args:
        cases: test cases to run

        Returns:
        The session returncode (0 for success)

        """
        batchspec = canary.config.getoption("canary_hpc_batchspec")
        if not batchspec:
            raise ValueError("Cannot partition test cases: missing batching options")
        specs: list[BatchSpec] = batch_testcases(
            cases=runner.cases,
            layout=batchspec["layout"],
            count=batchspec["count"],
            duration=batchspec["duration"],
            nodes=batchspec["nodes"],
        )
        if not specs:
            raise ValueError(
                "No test batches generated (this should never happen, "
                "the default batching scheme should have been used)"
            )
        if missing := {c.id for c in runner.cases} - {c.id for batch in specs for c in batch.cases}:
            raise ValueError(f"Test cases missing from batches: {', '.join(missing)}")

        fmt = "@*{Generated} %d batch specs from %d test cases"
        logger.info(fmt % (len(specs), len(runner.cases)))
        root = runner.cases[0].workspace.root.parent / "canary-hpc"
        batches: list[TestBatch] = []
        for spec in specs:
            path = f"batches/{spec.id[:8]}"
            workspace = ExecutionSpace(
                root=root, path=Path(path), session=runner.cases[0].workspace.session
            )
            batch = TestBatch(spec, workspace=workspace)
            batches.append(batch)
        queue = ResourceQueue(global_lock, resource_pool=self.rpool)
        queue.put(*batches)  # type: ignore
        queue.prepare()
        executor = BatchExecutor()
        max_workers = canary.config.getoption("workers") or 10
        with ResourceQueueExecutor(queue, executor, max_workers=max_workers) as ex:
            ex.run(backend=self.backend.name)

        return True

    @staticmethod
    def setup_parser(
        parser: "canary.Parser | LegacyParserAdapter | argparse._ArgumentGroup",
    ) -> None:
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

    @staticmethod
    def setup_legacy_parser(parser: canary.Parser) -> None:
        p = LegacyParserAdapter(parser)
        CanaryHPCConductor.setup_parser(p)


class LegacyParserAdapter:
    def __init__(self, parser: "canary.Parser") -> None:
        self.parser = parser
        self.parser.add_argument(
            "-b",
            command="run",
            group="canary hpc",
            metavar="option=value",
            action=CanaryHPCResourceSetter,
            help="Short cut for setting batch options.",
        )

    def add_argument(self, flag: str, *args, **kwargs):
        flag = "--hpc-" + flag[2:]
        self.parser.add_argument(flag, *args, command="run", group="canary hpc", **kwargs)

    def parse_args(self, args: Sequence[str] | None = None) -> argparse.Namespace:
        return self.parser.parse_args(args)


class KeyboardQuit(Exception):
    pass


class BatchExecutor:
    """Class for running ``ResourceQueue``."""

    def __call__(self, batch: TestBatch, queue: mp.Queue, **kwargs: Any) -> None:
        # Ensure the config is loaded, since this may be called in a new subprocess
        canary.config.ensure_loaded()
        backend = hpc_connect.get_backend(kwargs["backend"])
        batch.setup()
        batch.run(queue, backend=backend)
