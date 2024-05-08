from typing import Any

from ..third_party.schema import Optional
from ..third_party.schema import Or
from ..third_party.schema import Schema
from ..util.time import time_in_seconds


def list_of_str(arg: Any) -> bool:
    return isinstance(arg, list) and all([isinstance(_, str) for _ in arg])


def vardict(arg: Any) -> bool:
    if arg is None:
        return True
    if not isinstance(arg, dict):
        return False
    for key, value in arg.items():
        if not isinstance(key, str):
            return False
        if not isinstance(value, str):
            return False
    return True


def log_levels(arg: Any) -> bool:
    if not isinstance(arg, str):
        return False
    elif arg.upper() not in ("TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "FATAL"):
        return False
    return True


config_schema = Schema(
    {
        "config": {
            Optional("debug"): bool,
            Optional("no_cache"): bool,
            Optional("log_level"): log_levels,
        }
    }
)

test_schema = Schema(
    {
        "test": {
            "timeout": {
                Optional("fast"): time_in_seconds,
                Optional("long"): time_in_seconds,
                Optional("default"): time_in_seconds,
            }
        }
    }
)

machine_schema = Schema(
    {
        "machine": {
            Optional("nodes"): Or(int, None),
            Optional("cores_per_socket"): int,
            Optional("sockets_per_node"): int,
            Optional("cpu_count"): int,
            Optional("device_count"): int,
            Optional("devices_per_socket"): int,
        },
    }
)
python_schema = Schema({"python": {"executable": str, "version": str, "version_info": list}})
variables_schema = Schema({"variables": vardict})
testpaths_schema = Schema({"testpaths": [{"root": str, "paths": list_of_str}]})

build_schema = Schema(
    {
        "build": {
            Optional("project"): str,
            Optional("type"): str,
            Optional("date"): str,
            Optional("build_directory"): str,
            Optional("source_directory"): str,
            Optional("compiler"): {
                Optional("vendor"): str,
                Optional("version"): str,
                Optional("paths"): {
                    Optional("cc"): str,
                    Optional("cxx"): str,
                    Optional("fc"): str,
                },
            },
            Optional("options"): dict,
        }
    }
)

any_schema = Schema({}, ignore_extra_keys=True)
