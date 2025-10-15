# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""argparse.Action subclasses for canary_hpc batch options"""

import argparse
import os
import re
import shlex
from typing import Any

import canary
from _canary.util.string import csvsplit
from _canary.util.string import strip_quotes
from _canary.util.time import time_in_seconds

from . import partitioning

logger = canary.get_logger(__name__)


class CanaryHPCSchedulerArgs(argparse.Action):
    """Arguments to pass directly to scheduler"""

    @staticmethod
    def defaults() -> list[str]:
        options: list[str] = []
        if arg := os.getenv("CANARY_HPC_SCHEDULER_ARGS"):
            options.extend(shlex.split(arg))
        return options

    def __call__(self, parser, namespace, value, option_string=None):
        args = getattr(namespace, self.dest, None) or self.defaults()
        args.extend(self.parse(strip_quotes(value)))
        setattr(namespace, self.dest, args)

    @staticmethod
    def parse(arg: str) -> list[str]:
        return csvsplit(arg)


class CanaryHPCBatchExec(argparse.Action):
    "Arguments to determine how to partition test cases"

    def __call__(self, parser, namespace, value, option_string=None):
        spec = self.parse(strip_quotes(value))
        setattr(namespace, self.dest, spec)

    @staticmethod
    def parse(value: str) -> dict[str, str]:
        spec: dict[str, str] = {}
        for arg in csvsplit(value):
            if match := re.search(r"^backend[:=](.*)$", arg.lower()):
                spec["backend"] = match.group(1)
            elif match := re.search(r"^batch[:=](.*)$", arg.lower()):
                spec["batch"] = match.group(1)
            elif match := re.search(r"^case[:=](.*)$", arg.lower()):
                spec["case"] = match.group(1)
        if "backend" not in spec:
            raise ValueError("Batch exec spec missing required key 'backend'")
        if "batch" not in spec:
            raise ValueError("Batch exec spec missing required key 'batch'")
        return spec


class CanaryHPCBatchSpec(argparse.Action):
    @staticmethod
    def defaults() -> dict[str, Any]:
        return {"nodes": None, "layout": None, "count": None, "duration": None}

    def __call__(self, parser, namespace, value, option_string=None):
        spec = getattr(namespace, self.dest, None) or self.defaults()
        spec.update(self.parse(strip_quotes(value)))
        setattr(namespace, self.dest, spec)

    @staticmethod
    def parse(value: str) -> dict[str, Any]:
        spec: dict[str, Any] = {}
        for arg in csvsplit(value):
            if match := re.search(r"^nodes[:=](any|same)$", arg.lower()):
                spec["nodes"] = match.group(1)
            elif match := re.search(r"^layout[:=](flat|atomic)$", arg.lower()):
                spec["layout"] = match.group(1)
            elif match := re.search(r"^count[:=]([-]?\d+)$", arg.lower()):
                count = int(match.group(1))
                if count < 0:
                    raise ValueError("count <= -1")
                spec["count"] = count
            elif match := re.search(r"^count[:=]auto$", arg.lower()):
                spec["count"] = partitioning.AUTO
            elif match := re.search(r"^count[:=]max$", arg.lower()):
                spec["count"] = partitioning.ONE_PER_BUCKET
            elif match := re.search(r"^duration[:=](.*)$", arg.lower()):
                duration = time_in_seconds(match.group(1))
                if duration <= 0:
                    raise ValueError("batch duration <= 0")
                spec["duration"] = duration
            else:
                raise ValueError(f"invalid batch spec arg: {arg}")
        return spec

    @staticmethod
    def helppage() -> str:
        description = """\
Batch specification syntax:

  option=value[,option=value...]

option=value pairs:

    count: Partition test cases into this many batches
        auto: partition tests into batches taking approximately duration:T seconds
        max: partition test cases one test per batch.
        [0-9]+: partition test cases into at most this many batches.

    duration: Approximate total runtime of batches (implies count=auto)
        [0-9]+: approximate runtime in seconds.
          also accepts Go's duration format: 40s, 2h, 4h30m30s, etc.
    layout:
        flat: no test cases within a batch depend on test cases in the same batch
            Batches may depend on other batches.
        atomic: Test cases within a batch may depend on other test cases in the same batch
            Batches do not depend on other batches

    nodes:
        any: ignore node counts when batching.
        same: all tests in batch require same node count.

Examples:
    layout=flat,count=auto,nodes=same,duration=1800
        Partition test cases into batches with approximate runtime of 1800 seconds.

    layout=atomic,count=2
        Partition test cases into 2 batches.  Each batch will be independent.
"""
        return description

    @staticmethod
    def validate_and_set_defaults(spec: dict) -> None:
        if spec.get("duration") is None and spec.get("count") is None:
            spec["duration"] = 30 * 60  # 30 minutes
            spec["count"] = None
        if "duration" not in spec:
            spec["duration"] = None
        if "count" not in spec:
            spec["count"] = None
        if "nodes" not in spec:
            spec["nodes"] = "any"
        if spec["nodes"] is None:
            spec["nodes"] = "any"
        if "layout" not in spec:
            spec["layout"] = "flat"
        if spec["layout"] is None:
            spec["layout"] = "flat"
        if spec["duration"] is not None and spec["count"] is not None:
            raise ValueError("batch spec: duration not allowed with count")
        if spec["layout"] == "atomic" and spec["nodes"] == "same":
            raise ValueError("batch spec: layout:atomic not allowed with nodes:same")


class CanaryHPCResourceSetter(argparse.Action):
    """Set all options from -b option.  This is kept for backward compatibility"""

    def __call__(self, parser, namespace, value, option_string=None):
        if match := re.search(r"^spec=(.*)$", value):
            dest = "canary_hpc_batchspec"
            raw = strip_quotes(match.group(1))
            spec = getattr(namespace, dest, None) or CanaryHPCBatchSpec.defaults()
            spec.update(CanaryHPCBatchSpec.parse(raw))
            setattr(namespace, dest, spec)
        elif match := re.search(r"^exec=(.*)$", value):
            dest = "canary_hpc_batchexec"
            raw = strip_quotes(match.group(1))
            spec = CanaryHPCBatchExec.parse(raw)
            setattr(namespace, dest, spec)
        elif match := re.search(r"^workers[:=](\d+)$", value):
            workers = int(match.group(1))
            if workers <= 0:
                raise ValueError("batch workers <= 0")
            setattr(namespace, "canary_hpc_batch_workers", workers)
        elif match := re.search(r"^(backend|scheduler|type)[:=](\w+)$", value):
            raw = match.group(2)
            setattr(namespace, "canary_hpc_scheduler", raw)
        elif match := re.search(r"^timeout[:=](.+)$", value):
            raw = strip_quotes(match.group(1))
            if raw not in ("conservative", "agressive"):
                raise ValueError(f"Incorrect batch timeout choice: {raw}")
            setattr(namespace, "canary_hpc_batch_timeout_strategy", raw)
        elif match := re.search(r"^(option|args|options|with)[:=](.*)$", value):
            dest = "canary_hpc_scheduler_args"
            opts = getattr(namespace, dest, None) or CanaryHPCSchedulerArgs.defaults()
            raw = strip_quotes(match.group(2))
            opts.extend(CanaryHPCSchedulerArgs.parse(raw))
            setattr(namespace, dest, opts)
        else:
            raise ValueError(f"invalid batch value: {value!r}")
