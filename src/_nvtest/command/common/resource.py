import argparse
import re
import shlex
from typing import Any

from _nvtest.third_party.color import colorize
from _nvtest.util import logging
from _nvtest.util.string import ilist
from _nvtest.util.string import strip_quotes
from _nvtest.util.time import time_in_seconds


class ResourceSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        if option_string == "-b":
            if not values.startswith("batch:"):
                values = f"batch:{values}"
        key, value = ResourceSetter.parse(values, args)
        if key.startswith("batch_"):
            setattr(args, "batched_invocation", True)
        self.check_for_mutually_exclusive_arguments(args, key, value)
        if isinstance(value, list):
            old = getattr(args, key, [])
            old.extend(value)
            value = old
        setattr(args, key, value)

    @staticmethod
    def help_page(flag: str) -> str:
        text = """\
Defines resources that are required by the test session and establishes limits
to the amount of resources that can be consumed. The %(r_arg)s argument is of
the form: %(r_form)s.  The possible %(r_form)s settings are\n\n
• session:workers=N: Execute the test session asynchronously using a pool of at most N workers [default: auto]\n\n
• session:cpu_count=N: Occupy at most N cpu cores at any one time.\n\n
• session:cpu_ids=L: Comma separated list of CPU ids available to the session, mutually exclusive with session:cpu_count.\n\n
• session:gpu_count=N: Occupy at most N gpus at any one time.\n\n
• session:gpu_ids=L: Comma separated list of GPU ids available to the session, mutually exclusive with session:gpu_count.\n\n
• session:timeout=T: Set a timeout on test session execution in seconds (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s) [default: 60m]\n\n
• test:cpu_count=[n:]N: Skip tests requiring less than n and more than N cpu cores [default: [1, machine:cpu_count]]\n\n
• test:gpu_count=[n:]N: Skip tests requiring less than n and more than N gpus [default: [0, machine:gpu_count]]\n\n
• test:node_count=[n:]N: Skip tests requiring less than n and more than N nodes [default: [1, machine:node_count]]\n\n
• test:timeout=T: Set a timeout on any single test execution in seconds (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s)\n\n
• test:timeoutx=R: Set a timeout multiplier for all tests [default: 1.0]\n\n
• batch:count=N: Execute tests in N batches.\n\n
• batch:length=T: Execute tests in batches having runtimes of approximately T seconds.  [default: 30 min]\n\n
• batch:scheduler=S: Submit test batches to scheduler 'S'.\n\n
• batch:workers=N: Execute tests in a batch asynchronously using a pool of at most N workers [default: auto]\n\n
• batch:scheduler_args=A: Any additional args 'A' are passed directly to the scheduler,
  for example, batch:scheduler_args=--account=ABC will pass --account=ABC to the scheduler
""" % {"r_form": _bold("scope:type=value"), "r_arg": _bold(f"{flag} resource")}
        return text

    @staticmethod
    def parse(arg: str, namespace: argparse.Namespace) -> tuple[str, Any]:
        if match := re.search(r"^session:(cpu_count|cpus|cores|processors)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("session_cpu_count", int(raw))
        elif match := re.search(r"^session:cpu_ids[:=](.*)$", arg):
            raw = match.group(1)
            ints = ilist(raw.strip())
            return ("session_cpu_ids", ints)
        elif match := re.search(r"^session:(cpu_count|nodes)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("session_node_count", int(raw))
        elif match := re.search(r"^session:node_ids[:=](.*)$", arg):
            raw = match.group(1)
            ints = ilist(raw.strip())
            return ("session_node_ids", ints)
        elif match := re.search(r"^session:gpu_ids[:=](.*)$", arg):
            raw = match.group(1)
            ints = ilist(raw.strip())
            return ("session_gpu_ids", ints)
        elif match := re.search(r"^session:workers[:=](\d+)$", arg):
            raw = match.group(1)
            return ("session_workers", int(raw))
        elif match := re.search(r"^session:(gpu_count|gpus|devices)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("session_gpu_count", int(raw))
        elif match := re.search(r"^test:(gpu_count|gpus|devices)[:=]:?(\d+)$", arg):
            raw = match.group(2)
            return ("test_gpu_count", [1, int(raw)])
        elif match := re.search(r"^test:(gpu_count|gpus|devices)[:=](\d+):$", arg):
            raw = match.group(2)
            return ("test_gpu_count", [int(raw), None])
        elif match := re.search(r"^test:(gpu_count|gpus|devices)[:=](\d+):(\d+)$", arg):
            _, a, b = match.groups()
            return ("test_gpu_count", [int(a), int(b)])
        elif match := re.search(r"^test:(cpu_count|cpus|cores|processors)[:=]:?(\d+)$", arg):
            raw = match.group(2)
            return ("test_cpu_count", [1, int(raw)])
        elif match := re.search(r"^test:(cpu_count|cpus|cores|processors)[:=](\d+):$", arg):
            raw = match.group(2)
            return ("test_cpu_count", [int(raw), None])
        elif match := re.search(r"^test:(cpu_count|cpus|cores|processors)[:=](\d+):(\d+)$", arg):
            _, a, b = match.groups()
            return ("test_cpu_count", [int(a), int(b)])
        elif match := re.search(r"^test:(node_count|nodes)[:=]:?(\d+)$", arg):
            raw = match.group(2)
            return ("test_node_count", [1, int(raw)])
        elif match := re.search(r"^test:(node_count|nodes)[:=](\d+):$", arg):
            raw = match.group(2)
            return ("test_node_count", [int(raw), None])
        elif match := re.search(r"^test:(node_count|nodes)[:=](\d+):(\d+)$", arg):
            _, a, b = match.groups()
            return ("test_node_count", [int(a), int(b)])
        elif match := re.search(r"^(session|test):timeout[:=](.*)$", arg):
            scope, raw = match.group(1), strip_quotes(match.group(2))
            return (f"{scope}_timeout", time_in_seconds(raw))
        elif match := re.search(r"^test:timeoutx[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            return ("test_timeoutx", time_in_seconds(raw))
        elif match := re.search(r"^batch:length[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            length = time_in_seconds(raw)
            if length <= 0:
                raise ValueError("batch length <= 0")
            return ("batch_length", time_in_seconds(raw))
        elif match := re.search(r"^batch:(count|workers)[:=](\d+)$", arg):
            type, raw = match.groups()
            return (f"batch_{type}", int(raw))
        elif match := re.search(r"^batch:(runner|scheduler|type)[:=](\w+)$", arg):
            raw = match.group(2)
            return ("batch_scheduler", str(raw))
        elif match := re.search(r"^batch:(args|runner_args|scheduler_args)[:=](.*)$", arg):
            raw = strip_quotes(match.group(2))
            return ("batch_scheduler_args", shlex.split(raw))
        else:
            raise ValueError(f"invalid resource arg: {arg!r}")

    def check_for_mutually_exclusive_arguments(
        self, args: argparse.Namespace, key: str, value: Any
    ) -> None:
        if key == "session_cpu_count" and getattr(args, "session_cpu_ids", None) is not None:
            # last wins
            logging.warning("session:cpu_ids being overridden by session:cpu_count")
            args.session_cpu_ids = None
        elif key == "session_cpu_ids" and getattr(args, "session_cpu_count", None) is not None:
            logging.warning("session:cpu_count being overridden by session:cpu_ids")
            args.session_cpu_count = None
        elif key == "session_node_count" and getattr(args, "session_node_ids", None) is not None:
            # last wins
            logging.warning("session:node_ids being overridden by session:node_count")
            args.session_node_ids = None
        elif key == "session_node_ids" and getattr(args, "session_node_count", None) is not None:
            logging.warning("session:node_count being overridden by session:node_ids")
            args.session_node_count = None
        elif key == "session_gpu_count" and getattr(args, "session_gpu_ids", None) is not None:
            # last wins
            logging.warning("session:gpu_ids being overridden by session:gpu_count")
            args.session_gpu_ids = None
        elif key == "session_gpu_ids" and getattr(args, "session_gpu_count", None) is not None:
            logging.warning("session:gpu_count being overridden by session:gpu_ids")
            args.session_gpu_count = None
        elif key == "batch_length" and getattr(args, "batch_count", None) is not None:
            # last wins
            logging.warning("batch:count being overridden by batch:length")
            args.batch_count = None
        elif key == "batch_count" and getattr(args, "batch_length", None) is not None:
            # last wins
            logging.warning("batch:length being overridden by batch:count")
            args.batch_length = None


def _bold(arg: str) -> str:
    return colorize("@*{%s}" % arg)
