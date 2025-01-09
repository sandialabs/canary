import argparse
import re
from typing import Any

from _nvtest.third_party.color import colorize
from _nvtest.util import logging
from _nvtest.util.string import strip_quotes
from _nvtest.util.time import time_in_seconds


class DeprecatedResourceSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        prefix = f"[OPTION REMOVED]: '{option_string or '-l'} {values}'"
        if values.startswith("batch:"):
            BatchResourceSetter.consume("batch", args, values[6:], option_string)
            return
        pattern = r"(session)?(cpu_count|cpus|cores|processors|node_count|nodes|gpu_count|gpus).*"
        if match := re.search(pattern, values):
            parser.error(f"{prefix}: set resource limits via configuration settings")
        elif match := re.search(r"(session:)?workers[:=](\d+)$", values):
            raw = match.group(2)
            logging.warning(f"{prefix}: use --workers={raw}")
            setattr(args, "workers", int(raw))
            return
        elif match := re.search(r"(session:)?timeout[:=](.*)$", values):
            raw = strip_quotes(match.group(2))
            logging.warning(f"{prefix}: use --timeout={raw}")
            setattr(args, "timeout", time_in_seconds(raw))
            return
        elif match := re.search(r"^test:timeoutx[:=](.*)$", values):
            raw = strip_quotes(match.group(1))
            logging.warning(f"{prefix}: use --timeout-multiplier={raw}")
            setattr(args, "timeout_multiplier", float(raw))
        else:
            raise ValueError(f"invalid resource arg: {values!r}")


class BatchResourceSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        BatchResourceSetter.consume(self.dest, args, values, option_string)

    @staticmethod
    def consume(
        dest: str, args: argparse.Namespace, values: str, option_string: str | None
    ) -> None:
        key, value = BatchResourceSetter.parse(values, args)
        batch = getattr(args, dest) or {}
        if key == "duration":
            batch["scheme"] = "duration"
        elif key == "count":
            batch["scheme"] = "count"
        BatchResourceSetter.check_for_mutually_exclusive_arguments(batch, key, value, option_string)
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
• count=N: Execute tests in N batches.  Sets scheme=count\n\n
• duration=T: Execute tests in batches having runtimes of approximately T seconds.  Sets scheme=duration [default: 30 min]\n\n
• scheme=S: Partition tests into batches using the scheme {duration, count, isolate} [default: None]\n\n
• scheduler=S: Submit test batches to scheduler 'S'.\n\n
• workers=N: Execute tests in a batch asynchronously using a pool of at most N workers [default: auto]\n\n
• option=option: Pass *option* to the scheduler.  If *option* contains commas, it is split into multiple options at the commas.
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
            return ("duration", duration)
        elif match := re.search(r"^(count|workers)[:=](\d+)$", arg):
            type, raw = match.groups()
            return (type, int(raw))
        elif match := re.search(r"^scheme[:=](\w+)$", arg):
            raw = match.group(1)
            if raw not in ("count", "duration", "isolate"):
                raise ValueError(f"scheme={raw} not in (count, duration, isolate)")
            return ("scheme", raw)
        elif match := re.search(r"^(runner|scheduler|type)[:=](\w+)$", arg):
            raw = match.group(2)
            return ("scheduler", raw)
        elif match := re.search(r"^(option|args|scheduler_args)[:=](.*)$", arg):
            raw = strip_quotes(match.group(2))
            return ("options", [_.strip() for _ in raw.split(",") if _.split()])
        else:
            raise ValueError(f"invalid resource arg: {arg!r}")

    @staticmethod
    def check_for_mutually_exclusive_arguments(
        batch: dict[str, Any], key: str, value: Any, option_string: str | None
    ) -> None:
        opt = option_string or "-b"
        # last wins
        if key == "duration" and batch.get("count") is not None:
            old = batch.pop("count")
            logging.warning(f"{opt} count={old} being overridden by {opt} duration={value}")
        elif key == "count" and batch.get("duration") is not None:
            old = batch.pop("duration")
            logging.warning(f"{opt} duration={old} being overridden by {opt} count={value}")
        elif (key, value) == ("scheme", "isolate"):
            if batch.get("duration") is not None:
                old = batch.pop("duration")
                logging.warning(f"{opt} duration={old} being overridden by {opt} scheme=isolate")
            if batch.get("count") is not None:
                old = batch.pop("count")
                logging.warning(f"{opt} count={old} being overridden by {opt} scheme=isolate")
        elif (key, value) == ("scheme", "count"):
            if batch.get("duration") is not None:
                old = batch.pop("duration")
                logging.warning(f"{opt} duration={old} being overridden {opt} scheme=count")
        elif (key, value) == ("scheme", "duration"):
            if batch.get("count") is not None:
                old = batch.pop("count")
                logging.warning(f"{opt} count={old} being overridden by {opt} scheme=duration")


def _bold(arg: str) -> str:
    return colorize("@*{%s}" % arg)
