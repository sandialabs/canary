import argparse
import re
import shlex
import warnings
from typing import Any

from _nvtest.third_party.color import colorize
from _nvtest.util import logging
from _nvtest.util.string import ilist
from _nvtest.util.string import strip_quotes
from _nvtest.util.time import time_in_seconds


def _join(arg: list, sep: str = ",") -> str:
    return sep.join(str(_) for _ in arg)


class ResourceSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        if values.startswith("batch:"):
            BatchResourceSetter.consume(args, values, option_string)
        else:
            ResourceSetter.consume(args, values, option_string)

    @staticmethod
    def consume(args: argparse.Namespace, values: str, option_string: str | None) -> None:
        key, value = ResourceSetter.parse(values, args)
        ResourceSetter.check_for_mutually_exclusive_arguments(args, key, value, option_string)
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
• workers=N: Execute the test session asynchronously using a pool of at most N workers\n\n
• cpu_count=N: Occupy at most N cpu cores at any one time.\n\n
• gpu_count=N: Occupy at most N gpus at any one time.\n\n
• timeout=T: Set a timeout on test session execution in seconds (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s) [default: None]\n\n
""" % {"r_form": _bold("type=value"), "r_arg": _bold(f"{flag} resource")}
        return text

    @staticmethod
    def parse(arg: str, namespace: argparse.Namespace) -> tuple[str, Any]:
        if arg.startswith("session:"):
            arg = arg[8:]
        if match := re.search(r"^(cpu_count|cpus|cores|processors)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("session_cpu_count", int(raw))
        elif match := re.search(r"^cpu_ids[:=](.*)$", arg):
            raw = match.group(1)
            ints = ilist(raw.strip())
            return ("session_cpu_ids", ints)
        elif match := re.search(r"^(cpu_count|nodes)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("session_node_count", int(raw))
        elif match := re.search(r"^node_ids[:=](.*)$", arg):
            raw = match.group(1)
            ints = ilist(raw.strip())
            return ("session_node_ids", ints)
        elif match := re.search(r"^gpu_ids[:=](.*)$", arg):
            raw = match.group(1)
            ints = ilist(raw.strip())
            return ("session_gpu_ids", ints)
        elif match := re.search(r"^workers[:=](\d+)$", arg):
            raw = match.group(1)
            return ("session_workers", int(raw))
        elif match := re.search(r"^timeout[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            return ("session_timeout", time_in_seconds(raw))
        elif match := re.search(r"^(gpu_count|gpus|devices)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("session_gpu_count", int(raw))
        elif match := re.search(r"^test:timeoutx[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            warnings.warn(f"prefer --timeout-multiplier={raw} to {arg}", DeprecationWarning)
            return ("timeout_multiplier", float(raw))
        else:
            raise ValueError(f"invalid resource arg: {arg!r}")

    @staticmethod
    def check_for_mutually_exclusive_arguments(
        args: argparse.Namespace, key: str, value: Any, option_string: str | None
    ) -> None:
        # last wins
        opt = option_string or "-l"
        if key == "session_cpu_count" and getattr(args, "session_cpu_ids", None) is not None:
            old = _join(args.session_cpu_ids)
            logging.warning(f"{opt} cpu_ids={old} being overridden by {opt} cpu_count={value}")
            args.session_cpu_ids = None
        elif key == "session_cpu_ids" and getattr(args, "session_cpu_count", None) is not None:
            old, new = args.session_cpu_count, _join(value)
            logging.warning(f"{opt} cpu_count={old} being overridden by {opt} cpu_ids={new}")
            args.session_cpu_count = None
        elif key == "session_node_count" and getattr(args, "session_node_ids", None) is not None:
            old = _join(args.session_node_ids)
            logging.warning(f"{opt} node_ids={old} being overridden by {opt} node_count={value}")
            args.session_node_ids = None
        elif key == "session_node_ids" and getattr(args, "session_node_count", None) is not None:
            old, new = args.session_node_count, _join(value)
            logging.warning(f"{opt} node_count={old} being overridden by {opt} node_ids={new}")
            args.session_node_count = None
        elif key == "session_gpu_count" and getattr(args, "session_gpu_ids", None) is not None:
            old = _join(args.session_gpu_ids)
            logging.warning(f"{opt} gpu_ids={old} being overridden by {opt} gpu_count={value}")
            args.session_gpu_ids = None
        elif key == "session_gpu_ids" and getattr(args, "session_gpu_count", None) is not None:
            old, new = args.session_gpu_count, _join(value)
            logging.warning(f"{opt} gpu_count={old} being overridden by {opt} gpu_ids={new}")
            args.session_gpu_count = None


class BatchResourceSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        setattr(args, self.dest, True)
        self.consume(args, values, option_string)

    @staticmethod
    def consume(args: argparse.Namespace, values: str, option_string: str | None) -> None:
        key, value = BatchResourceSetter.parse(values, args)
        if key == "batch_duration":
            setattr(args, "batch_scheme", "duration")
        elif key == "batch_count":
            setattr(args, "batch_scheme", "count")
        BatchResourceSetter.check_for_mutually_exclusive_arguments(args, key, value, option_string)
        if isinstance(value, list):
            old = getattr(args, key, [])
            old.extend(value)
            value = old
        setattr(args, key, value)

    @staticmethod
    def help_page(flag: str) -> str:
        text = """\
Defines resources required to batch and schedule test batches. The %(r_arg)s argument is of
the form: %(r_form)s.  The possible %(r_form)s settings are\n\n
• count=N: Execute tests in N batches.  Sets scheme=count\n\n
• duration=T: Execute tests in batches having runtimes of approximately T seconds.  Sets scheme=duration [default: 30 min]\n\n
• scheme=S: Partition tests into batches using the scheme {duration, count, isolate} [default: None]\n\n
• scheduler=S: Submit test batches to scheduler 'S'.\n\n
• workers=N: Execute tests in a batch asynchronously using a pool of at most N workers [default: auto]\n\n
• scheduler_args=A: Any additional args 'A' are passed directly to the scheduler,
  for example, scheduler_args=--account=ABC will pass --account=ABC to the scheduler
""" % {"r_form": _bold("type=value"), "r_arg": _bold(f"{flag} resource")}
        return text

    @staticmethod
    def parse(arg: str, namespace: argparse.Namespace) -> tuple[str, Any]:
        if arg.startswith("batch:"):
            arg = arg[6:]
        if match := re.search(r"^(duration|length)[:=](.*)$", arg):
            raw = strip_quotes(match.group(2))
            duration = time_in_seconds(raw)
            if duration <= 0:
                raise ValueError("batch duration <= 0")
            return ("batch_duration", duration)
        elif match := re.search(r"^(count|workers)[:=](\d+)$", arg):
            type, raw = match.groups()
            return (f"batch_{type}", int(raw))
        elif match := re.search(r"^scheme[:=](\w+)$", arg):
            raw = match.group(1)
            if raw not in ("count", "duration", "isolate"):
                raise ValueError(f"scheme={raw} not in (count, duration, isolate)")
            return ("batch_scheme", str(raw))
        elif match := re.search(r"^(runner|scheduler|type)[:=](\w+)$", arg):
            raw = match.group(2)
            return ("batch_scheduler", str(raw))
        elif match := re.search(r"^(args|runner_args|scheduler_args)[:=](.*)$", arg):
            raw = strip_quotes(match.group(2))
            return ("batch_scheduler_args", shlex.split(raw))
        else:
            raise ValueError(f"invalid resource arg: {arg!r}")

    @staticmethod
    def check_for_mutually_exclusive_arguments(
        args: argparse.Namespace, key: str, value: Any, option_string: str | None
    ) -> None:
        opt = option_string or "-b"
        if key == "batch_duration" and getattr(args, "batch_count", None) is not None:
            # last wins
            old = args.batch_count
            logging.warning(f"{opt} count={old} being overridden by {opt} duration={value}")
            args.batch_count = None
        elif key == "batch_count" and getattr(args, "batch_duration", None) is not None:
            # last wins
            old = args.batch_duration
            logging.warning(f"{opt} duration={old} being overridden by {opt} count={value}")
            args.batch_duration = None
        elif (key, value) == ("batch_scheme", "isolate"):
            # last wins
            if getattr(args, "batch_duration", None) is not None:
                old = args.batch_duration
                logging.warning(f"{opt} duration={old} being overridden by {opt} scheme=isolate")
                args.batch_duration = None
            if getattr(args, "batch_count", None) is not None:
                old = args.batch_count
                logging.warning(f"{opt} count={old} being overridden by {opt} scheme=isolate")
                args.batch_count = None
        elif (key, value) == ("batch_scheme", "count"):
            if getattr(args, "batch_duration", None) is not None:
                # last wins
                old = args.batch_duration
                logging.warning(f"{opt} duration={old} being overridden {opt} scheme=count")
                args.batch_duration = None
        elif (key, value) == ("batch_scheme", "duration"):
            if getattr(args, "batch_count", None) is not None:
                old = args.batch_count
                logging.warning(f"{opt} count={old} being overridden by {opt} scheme=duration")
                args.batch_count = None


def _bold(arg: str) -> str:
    return colorize("@*{%s}" % arg)
