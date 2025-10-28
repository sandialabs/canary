import argparse
import os
import re
import shutil
import subprocess
from collections import Counter
from typing import TYPE_CHECKING
from typing import Any

import psutil
import yaml

from ...resource_pool.schemas import resource_pool_schema
from ...util import logging
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...config import Config
    from ...config.argparsing import Parser


logger = logging.get_logger(__name__)
resource_regex = r"^([a-zA-Z_][a-zA-Z0-9_]*?)[:=](\d+)$"


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "-r",
        type=resource_t,
        action=update_action,
        dest="resource_pool_mods",
        metavar="TYPE=N",
        group="resource control",
        help=f"N instances of resource TYPE are available [default: cpus={psutil.cpu_count()}]",
    )
    parser.add_argument(
        "--resource-pool-file",
        dest="resource_pool_file",
        metavar="FILE",
        group="resource control",
        help="Read resource pool from this JSON or YAML file",
    )
    parser.add_argument(
        "--oversubscribe",
        action=update_action,
        type=resource_t,
        metavar="TYPE=N",
        command=("run", "config"),
        group="resource control",
        help="Apply the multiplier N to the number of slots available "
        "per resource instance of type TYPE",
    )


@hookimpl(tryfirst=True, specname="canary_resource_pool_fill")
def initialize_resource_pool_counts(config: "Config", pool: dict[str, dict[str, Any]]) -> None:
    resources: dict[str, list[dict[str, Any]]] = pool["resources"]
    resources["cpus"] = [{"id": str(j), "slots": 1} for j in range(psutil.cpu_count())]
    resources["gpus"] = []


@hookimpl(specname="canary_resource_pool_fill")
def fill_resource_pool_gpu_counts_nvidia(config: "Config", pool: dict[str, dict[str, Any]]) -> None:
    if nvidia_smi := shutil.which("nvidia-smi"):
        gpu_ids: list[str] = []
        args = [nvidia_smi, "--list-gpus"]
        try:
            p = subprocess.run(args, stdout=subprocess.PIPE, text=True)
            for line in p.stdout.split("\n"):
                if match := re.search("GPU (\d+):", line):
                    gpu_ids.append(match.group(1))
            pool["resources"]["gpus"] = [{"id": gpu_id, "slots": 1} for gpu_id in gpu_ids]
        except Exception:
            logger.debug(f"Failed to determine GPU counts from {nvidia_smi} --list-gpus")


@hookimpl(trylast=True, specname="canary_resource_pool_fill")
def finalize_resource_pool_counts(config: "Config", pool: dict[str, dict[str, Any]]) -> None:
    # Command line options take precedence, so they are filled last and overwrite whatever else is
    # present
    resources: dict[str, list[dict[str, Any]]] = pool["resources"]
    if f := config.getoption("resource_pool_file"):
        pool["additional_properties"]["resource_pool_file"] = os.path.abspath(f)
        with open(f) as fh:
            data = yaml.safe_load(fh)
            validated = resource_pool_schema.validate(data["resource_pool"])
        for rtype, rspec in validated["resources"].items():
            resources[rtype] = rspec

    slots_per_rtype: Counter[str] = Counter()
    errors: int = 0
    if rp := config.getoption("resource_pool_mods"):
        for key, count in rp.items():
            if key.startswith("slots_per_"):
                rtype = key[10:]
                if not rtype.endswith("s"):
                    rtype += "s"
                if rtype not in resources or rtype not in rp:
                    errors += 1
                    logger.error(
                        f"Cannot define {key}={count} since {rtype} "
                        f"is not a defined resource pool member"
                    )
                    continue
                slots_per_rtype[rtype] = count
            else:
                rtype = key
                if not rtype.endswith("s"):
                    rtype += "s"
                resources[rtype] = [{"id": str(j), "slots": 1} for j in range(count)]
    if oversubscribe := config.getoption("oversubscribe"):
        for key, count in oversubscribe.items():
            rtype = key
            if not rtype.endswith("s"):
                rtype += "s"
            if rtype not in resources:
                errors += 1
                logger.error(
                    f"Cannot define --oversubscribe={key}:{count} since {rtype} "
                    f"is not a defined resource pool member"
                )
            slots_per_rtype[rtype] = count
    if errors:
        raise ValueError("Stopping due to previous errors")

    for rtype, count in slots_per_rtype.items():
        for instance in resources[rtype]:
            instance["slots"] *= count


def resource_t(arg: str) -> dict[str, int]:
    if match := re.search(resource_regex, arg):
        type = match.group(1)
        count = int(match.group(2))
        return {type: count}
    raise ValueError(f"Unable to determine resource type and count from {arg}")


class update_action(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        result = getattr(namespace, self.dest, None) or {}
        for key, value in values.items():
            result[key] = value
        setattr(namespace, self.dest, result)
