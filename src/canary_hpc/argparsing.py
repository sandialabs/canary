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
    "Arguments to determine how to partition test jobs"

    def __call__(self, parser, namespace, value, option_string=None):
        spec = self.parse(strip_quotes(value))
        setattr(namespace, self.dest, spec)

    @staticmethod
    def parse(value: str) -> dict[str, str]:
        spec: dict[str, str] = {}
        for arg in csvsplit(value):
            lowered = arg.lower()

            if match := re.search(r"^backend[:=](.*)$", lowered):
                spec["backend"] = match.group(1)
            elif match := re.search(r"^batch[:=](.*)$", lowered):
                spec["batch"] = match.group(1)
            elif match := re.search(r"^job[:=](.*)$", lowered):
                spec["job"] = match.group(1)

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
            lowered = arg.lower()

            if match := re.search(r"^nodes[:=](any|same)$", lowered):
                spec["nodes"] = match.group(1)

            elif match := re.search(r"^layout[:=](flat|atomic)$", lowered):
                spec["layout"] = match.group(1)

            elif match := re.search(r"^count[:=]([-]?\d+)$", lowered):
                count = int(match.group(1))
                if count <= 0:
                    raise ValueError("count <= 0")
                spec["count"] = count

            elif re.search(r"^count[:=]max$", lowered):
                spec["count"] = "max"

            elif re.search(r"^count[:=]auto$", lowered):
                raise ValueError("count=auto is no longer supported; use duration=T")

            elif match := re.search(r"^duration[:=](.*)$", lowered):
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
    Batch specification syntax

    A batch spec controls how Canary HPC groups test jobs into batches.

    Syntax:
        option=value[,option=value...]

    Notes:
    - Comma-separated option=value pairs
    - Order does not matter
    - Unknown options/values are invalid
    - Scheduler simulation width is computed by the HPC integration layer as:
          node_count * cpus_per_node
      It is not a user-facing batch-spec option.

    Options:

      count
          Controls how many batches are created.

          count=max
              create the maximum number of batches allowed by the selected layout.

              For layout=flat:
                  one test job per batch.

              For layout=atomic:
                  one dependency-connected component per batch.

          count=N
              N is [1-9][0-9]*. Partition test jobs into at most N batches.

      duration
          Target approximate simulated runtime per batch.

          duration=N
              N is [0-9]+ seconds.

          duration=<go-duration>
              Go duration syntax such as: 40s, 2h, 4h30m30s, 45m

          Notes:
              Duration-targeted packing is currently supported for layout=flat.

      layout
          Controls dependency rules within and between batches.

          layout=flat (default)
              Jobs within a batch do NOT depend on each other.
              Batches MAY depend on other batches.

      layout=atomic
          Jobs within a batch MAY depend on each other.
          Batches do NOT depend on other batches.
          Defaults to nodes=any,count=max if no count is supplied.
          Duration-targeted atomic batching is not supported.

      nodes
          Controls whether tests in a batch must request the same node count.

          nodes=same (default)
              All test jobs in a batch require the same number of nodes.

          nodes=any
              Jobs within a batch may require different numbers of nodes.

    Examples:

      1) Time-targeted batching
          layout=flat,nodes=same,duration=1800
              Create flat batches of approximately 1800 simulated seconds each.

      2) Independent atomic batches
          layout=atomic,nodes=any,count=2
              Partition dependency-connected components into at most 2
              independent batches.

      3) One test/component per batch
          count=max

      4) Limit the number of batches
          count=4

      5) Allow mixed node counts within a batch
          nodes=any,duration=30m
              Create ~30-minute batches, allowing tests with different node counts
              in the same batch."""
        return description

    @staticmethod
    def validate_and_set_defaults(spec: dict) -> None:
        spec.setdefault("duration", None)
        spec.setdefault("count", None)
        spec.setdefault("layout", None)
        spec.setdefault("nodes", None)

        if spec["layout"] is None:
            spec["layout"] = "flat"

        if spec["layout"] not in ("flat", "atomic"):
            raise ValueError(f"batch spec: invalid layout value {spec['layout']!r}")

        # Atomic defaults to nodes=any unless user explicitly gave nodes=same.
        if spec["nodes"] is None:
            spec["nodes"] = "any" if spec["layout"] == "atomic" else "same"

        if spec["nodes"] not in ("any", "same"):
            raise ValueError(f"batch spec: invalid nodes value {spec['nodes']!r}")

        # Layout-aware default batching mode.
        if spec["duration"] is None and spec["count"] is None:
            if spec["layout"] == "atomic":
                spec["count"] = "max"
            else:
                spec["duration"] = 30 * 60  # 30 minutes

        if spec["duration"] is not None and spec["count"] is not None:
            raise ValueError("batch spec: duration not allowed with count")

        if spec["count"] is not None:
            count = spec["count"]
            if count != "max" and not isinstance(count, int):
                raise ValueError(f"batch spec: invalid count value {count!r}")
            if isinstance(count, int) and count <= 0:
                raise ValueError("batch spec: count <= 0")

        if spec["layout"] == "atomic" and spec["nodes"] != "any":
            raise ValueError("batch spec: layout=atomic requires nodes=any")

        if spec["duration"] is not None and spec["layout"] == "atomic":
            raise ValueError("batch spec: duration-targeted atomic layout is not supported")


class CanaryHPCResourceSetter(argparse.Action):
    """Set all options from -b option.  This is kept for backward compatibility"""

    def __call__(self, parser, namespace, value, option_string=None):
        if match := re.search(r"^spec=(.*)$", value):
            dest = "hpc_batchspec"
            raw = strip_quotes(match.group(1))
            spec = getattr(namespace, dest, None) or CanaryHPCBatchSpec.defaults()
            spec.update(CanaryHPCBatchSpec.parse(raw))
            setattr(namespace, dest, spec)

        elif match := re.search(r"^exec=(.*)$", value):
            dest = "hpc_batchexec"
            raw = strip_quotes(match.group(1))
            spec = CanaryHPCBatchExec.parse(raw)
            setattr(namespace, dest, spec)

        elif match := re.search(r"^workers[:=](\d+)$", value):
            workers = int(match.group(1))
            if workers <= 0:
                raise ValueError("batch workers <= 0")
            setattr(namespace, "hpc_batch_workers", workers)

        elif match := re.search(r"^(backend|scheduler|type)[:=](.+)$", value):
            raw = match.group(2)
            setattr(namespace, "hpc_backend", raw)

        elif match := re.search(r"^timeout[:=](.+)$", value):
            raw = strip_quotes(match.group(1))
            if raw == "agressive":
                raw = "aggressive"
            if raw not in ("conservative", "aggressive"):
                raise ValueError(f"Incorrect batch timeout choice: {raw}")
            setattr(namespace, "hpc_batch_timeout_strategy", raw)

        elif match := re.search(r"^queue_timeout[:=](.+)$", value):
            raw = strip_quotes(match.group(1))
            setattr(namespace, "hpc_queue_timeout", time_in_seconds(raw))

        elif match := re.search(r"^(option|args|options|with)[:=](.*)$", value):
            dest = "hpc_scheduler_args"
            opts = getattr(namespace, dest, None) or CanaryHPCSchedulerArgs.defaults()
            raw = strip_quotes(match.group(2))
            opts.extend(CanaryHPCSchedulerArgs.parse(raw))
            setattr(namespace, dest, opts)

        else:
            raise ValueError(f"invalid batch value: {value!r}")
