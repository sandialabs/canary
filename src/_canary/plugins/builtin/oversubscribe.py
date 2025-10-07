import argparse
import re
from typing import TYPE_CHECKING

from ...util import logging
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...config import Config
    from ...config.argparsing import Parser


logger = logging.get_logger(__name__)


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "--oversubscribe",
        action=Oversubscribe,
        metavar="TYPE=N",
        command=("run", "config"),
        group="resource control",
        help="Apply the multiplier N to the number of slots available "
        "per resource instance of type TYPE",
    )


@hookimpl(trylast=True)
def canary_configure(config: "Config") -> None:
    multipliers: dict[str, int] = {}
    if config_mods := config.getoption("config_mods"):
        if rp := config_mods.get("resource_pool"):
            for rtype, count in rp.items():
                if rtype.startswith("slots_per_"):
                    type = rtype[10:]
                    type = type if type.endswith("s") else f"{type}s"
                    logger.warning(
                        f"DEPRECATED: canary -c resource_pool:{rtype}:{count} ..., "
                        f"prefer canary run --oversubscribe {type}={count}"
                    )
                    multipliers[type] = count
                    if rtype in config.resource_pool:
                        config.resource_pool.pop(rtype)
    if oversubscribe := config.getoption("oversubscribe"):
        multipliers.update(oversubscribe)
    for type, multiplier in multipliers.items():
        for rtype, instances in config.resource_pool.resources.items():
            if type == rtype:
                for instance in instances:
                    instance["slots"] *= multiplier
                break
        else:
            raise ValueError(
                f"Attempting to allow oversubscription for unknown resource type {type!r}"
            )


class Oversubscribe(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        oversubscribe: dict[str, int] = getattr(namespace, self.dest) or {}
        if match := re.search(r"^([a-zA-Z_][a-zA-Z0-9_]*?)[:=](\d+)$", value.strip()):
            type = match.group(1)
            count = int(match.group(2))
        else:
            raise ValueError(f"Incorrect specification for {option_string}, expected TYPE=N")
        oversubscribe[type] = count
        setattr(namespace, self.dest, oversubscribe)
