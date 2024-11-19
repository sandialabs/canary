from typing import Any

from ..third_party.schema import Optional
from ..third_party.schema import Or
from ..third_party.schema import Schema
from ..util.time import time_in_seconds


def list_of_str(arg: Any) -> bool:
    return isinstance(arg, list) and all([isinstance(_, str) for _ in arg])


def list_of_int(arg: Any) -> bool:
    return isinstance(arg, list) and all([isinstance(_, int) for _ in arg])


optional_dict = Or(dict, None)
optional_int = Or(int, None)
optional_str = Or(str, None)


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
            Optional("cache_runtimes"): bool,
            Optional("log_level"): log_levels,
        }
    }
)


batch_schema = Schema({"batch": {Optional("length"): time_in_seconds}})

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
            Optional("node_count"): optional_int,
            Optional("cpus_per_node"): int,
            Optional("gpus_per_node"): int,
        },
    }
)
python_schema = Schema({"python": {"executable": str, "version": str, "version_info": list}})
variables_schema = Schema({"variables": vardict})
testpaths_schema = Schema({"testpaths": [{"root": str, "paths": list_of_str}]})

build_schema = Schema(
    {
        "build": {
            Optional("project"): optional_str,
            Optional("type"): optional_str,
            Optional("date"): optional_str,
            Optional("build_directory"): optional_str,
            Optional("source_directory"): optional_str,
            Optional("compiler"): {
                Optional("vendor"): optional_str,
                Optional("version"): optional_str,
                Optional("paths"): {
                    Optional("cc"): optional_str,
                    Optional("cxx"): optional_str,
                    Optional("fc"): optional_str,
                    Optional("mpicc"): optional_str,
                    Optional("mpicxx"): optional_str,
                    Optional("mpifc"): optional_str,
                },
                Optional("cc"): optional_str,
                Optional("cxx"): optional_str,
                Optional("fc"): optional_str,
                Optional("mpicc"): optional_str,
                Optional("mpicxx"): optional_str,
                Optional("mpifc"): optional_str,
            },
            Optional("options"): optional_dict,
        }
    },
    ignore_extra_keys=True,
)

any_schema = Schema({}, ignore_extra_keys=True)
