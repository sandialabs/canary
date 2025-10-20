import argparse
import re
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
rspec_type = dict[str, list[dict[str, Any]]]


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "-r",
        type=resource_t,
        action=update_action,
        dest="resource_pool_mods",
        metavar="TYPE=N",
        help=f"N instances of resource TYPE are available [default: cpus={psutil.cpu_count()}]",
    )
    parser.add_argument(
        "--resource-pool-file",
        dest="resource_pool_file",
        metavar="FILE",
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


@hookimpl(tryfirst=True, specname="canary_fill_resource_pool")
def initialize_resource_pool_counts(config: "Config", resources: rspec_type) -> None:
    resources["cpus"] = [{"id": str(j), "slots": 1} for j in range(psutil.cpu_count())]
    resources["gpus"] = []


@hookimpl(trylast=True, specname="canary_fill_resource_pool")
def finalize_resource_pool_counts(config: "Config", resources: rspec_type) -> None:
    # Command line options take precedence, so they are filled last and overwrite whatever else is
    # present
    if f := config.getoption("resource_pool_file"):
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
