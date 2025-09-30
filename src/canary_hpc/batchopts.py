# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import re
import shlex
from typing import Any

import canary
from _canary.third_party.color import colorize
from _canary.util.string import csvsplit
from _canary.util.string import strip_quotes
from _canary.util.time import time_in_seconds

from . import partitioning

logger = canary.get_logger(__name__)


class BatchResourceSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        BatchResourceSetter.consume(self.dest, args, values, option_string)

    @staticmethod
    def consume(
        dest: str, args: argparse.Namespace, values: str, option_string: str | None
    ) -> None:
        key, value = BatchResourceSetter.parse(values, args)
        if key == ".ignore":
            return
        batch = getattr(args, dest) or {}
        if isinstance(value, list):
            old = batch.get(key, [])
            old.extend(value)
            value = old
        batch[key] = value
        setattr(args, dest, batch)

    @staticmethod
    def help_page(flag: str) -> str:
        text = """\
Defines resources required to batch and schedule test batches. The %(r_arg)s argument is of
the form: %(r_form)s.  The possible %(r_form)s settings are\n\n
• backend=NAME: Submit test batches to this backend's scheduler 'S'.\n\n
• workers=N: Execute tests in a batch asynchronously using a pool of at most N workers [default: auto]\n\n
• option=%(opt)s: Pass %(opt)s to the backend's scheduler.  If %(opt)s contains commas, it is split into multiple options at the commas.\n\n
• spec=%(spec)s: Batch spec with possible option:value pairs:\n\n
[pad]%(count)s: Batch count.  max: one test per batch.  N>=1: split into at most N batches.\n\n
[pad]%(duration)s: Group tests into batches with total runtime approximate T seconds (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s).\n\n
[pad]%(layout)s: flat: batches may depend on other batches. atomic: each batch includes all dependencies and is self-contained.\n\n
[pad]%(nodes)s: any: ignore node counts when batching.  same: all tests in batch require same node count.
""" % {
            "r_form": bold("type=value"),
            "r_arg": bold(f"{flag} resource"),
            "opt": bold("option"),
            "spec": bold("option:value[,option:value...]"),
            "count": bold("count:{max,auto,N}}"),
            "duration": bold("duration:T"),
            "layout": bold("layout:{flat,atomic}}"),
            "nodes": bold("nodes:{any,same}}"),
        }
        return text

    @staticmethod
    def parse_spec(spec_arg: str, spec: dict[str, Any]) -> None:
        """Parse the -b spec=... option"""
        for arg in csvsplit(spec_arg):
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
                spec["count"] = partitioning.ONE_PER_BATCH
            elif match := re.search(r"^duration[:=](.*)$", arg.lower()):
                duration = time_in_seconds(match.group(1))
                if duration <= 0:
                    raise ValueError("batch duration <= 0")
                spec["duration"] = duration
            else:
                raise ValueError(f"invalid batch spec arg: {arg}")

    @staticmethod
    def parse_execspec(arg_in: str) -> dict[str, str]:
        """Parse the -b exec=... option"""
        spec: dict[str, str] = {}
        for arg in csvsplit(arg_in):
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

    @staticmethod
    def parse(arg: str, namespace: argparse.Namespace) -> tuple[str, Any]:
        if match := re.search(r"^exec=(.*)$", arg):
            raw = strip_quotes(match.group(1))
            execspec = BatchResourceSetter.parse_execspec(raw)
            return ("exec", execspec)
        elif match := re.search(r"^spec=(.*)$", arg):
            spec = setdefaultspec(namespace)
            raw = strip_quotes(match.group(1))
            BatchResourceSetter.parse_spec(raw, spec=spec)
            return ("spec", spec)
        elif match := re.search(r"^workers[:=](\d+)$", arg):
            workers = int(match.group(1))
            if workers <= 0:
                raise ValueError("batch workers <= 0")
            return ("workers", workers)
        elif match := re.search(r"^(backend|scheduler|type)[:=](\w+)$", arg):
            raw = match.group(2)
            return ("backend", raw)
        elif match := re.search(r"^(option|args|options|with)[:=](.*)$", arg):
            setdefaultopts(namespace)
            raw = strip_quotes(match.group(2))
            return ("options", csvsplit(raw))
        # Deprecated options, use spec
        if match := re.search(r"^(duration|length)[:=](.*)$", arg):
            a = match.group(1)
            raw = strip_quotes(match.group(2))
            logger.warning(f"Deprecated syntax: -b {a}={raw}, use -b spec=duration:{raw}[,...]")
            duration = time_in_seconds(raw)
            if duration <= 0:
                raise ValueError("batch duration <= 0")
            spec = setdefaultspec(namespace)
            spec["duration"] = duration
            return ("spec", spec)
        elif match := re.search(r"^count[:=]([-]?\d+)$", arg):
            raw = match.group(1)
            logger.warning(f"Deprecated syntax: -b count={raw}, use -b spec=count:{raw}[,...]")
            count = int(raw)
            if count < -1:
                raise ValueError("batch count < -1")
            spec = setdefaultspec(namespace)
            spec["count"] = count
            return ("spec", spec)
        elif match := re.search(r"^scheme[:=](isolate.*)$", arg):
            raw = match.group(1)
            logger.warning(f"Deprecated syntax: -b scheme={raw}, use -b spec=layout:flat[,...]")
            spec = setdefaultspec(namespace)
            spec["layout"] = "flat"
            return ("spec", spec)
        elif match := re.search(r"^scheme[:=](\w+)$", arg):
            raw = match.group(1)
            logger.warning(f"Deprecated syntax: -b scheme={raw}, use -b spec={raw}:...")
            return (".ignore", None)
        else:
            raise ValueError(f"invalid resource arg: {arg!r}")

    @staticmethod
    def validate_and_set_defaults(batchopts: dict) -> None:
        if execopts := batchopts.get("exec"):
            if len(batchopts) > 1:
                raise ValueError("-b exec= is mutually exclusive with any other -b options")
            if "batch" not in execopts:
                raise ValueError("Batch exec spec missing required key 'batch'")
            if "backend" not in batchopts["exec"]:
                raise ValueError("Batch exec spec missing required key 'backend'")
            return
        default_spec = {"nodes": "any", "layout": "flat", "count": None, "duration": 30 * 60}
        batchopts.setdefault("spec", default_spec)
        spec = batchopts["spec"]
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
        batchopts["spec"] = spec


def bold(arg: str) -> str:
    if os.getenv("COLOR_WHEN", "auto") == "never":
        return f"**{arg}**"
    return colorize("@*{%s}" % arg)


def setdefaultspec(namespace: argparse.Namespace) -> dict[str, Any]:
    default = {"nodes": None, "layout": None, "count": None, "duration": None}
    if not getattr(namespace, "batchopts", None):
        namespace.batchopts = {}
    namespace.batchopts.setdefault("spec", default)
    return namespace.batchopts["spec"]


def setdefaultopts(namespace: argparse.Namespace) -> list[str]:
    if not getattr(namespace, "batchopts", None):
        namespace.batchopts = {}
    if "options" not in namespace.batchopts:
        options = namespace.batchopts.setdefault("options", [])
        options.extend(list(canary.config.get("batch:default_options") or []))
        if arg := os.getenv("CANARY_BATCH_ARGS"):
            options.extend(shlex.split(arg))
    return namespace.batchopts["options"]
