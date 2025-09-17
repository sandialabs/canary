# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import typing

from ..third_party.schema import And
from ..third_party.schema import Optional
from ..third_party.schema import Or
from ..third_party.schema import Schema
from ..third_party.schema import Use
from ..util.time import time_in_seconds


def list_of_str(arg: typing.Any) -> bool:
    return isinstance(arg, list) and all([isinstance(_, str) for _ in arg])


def list_of_int(arg: typing.Any) -> bool:
    return isinstance(arg, list) and all([isinstance(_, int) for _ in arg])


optional_dict = Or(dict, None)
optional_str = Or(str, None)


def vardict(arg: typing.Any) -> bool:
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


def log_levels(arg: typing.Any) -> bool:
    if not isinstance(arg, str):
        return False
    elif arg.upper() not in ("TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "FATAL"):
        return False
    return True


def multiprocessing_contexts(arg: typing.Any) -> bool:
    if not isinstance(arg, str):
        return False
    elif arg.upper() not in ("FORK", "SPAWN"):
        return False
    return True


def boolean(arg: typing.Any) -> bool:
    if isinstance(arg, str):
        return arg.lower() in ("0", "off", "false", "no")
    return bool(arg)


positive_int = And(int, lambda x: x > 0)
nonnegative_int = And(int, lambda x: x >= 0)
id_list = Schema([{"id": Use(str), Optional("slots", default=1): Or(int, float)}])

any_schema = Schema({}, ignore_extra_keys=True)
machine_schema = Schema(
    {
        Optional("node_count"): int,
        Optional("cpus_per_node"): int,
        Optional("gpus_per_node"): int,
    }
)
build_schema = Schema(
    {
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
    },
    ignore_extra_keys=True,
)
config_schema = Schema(
    {
        Optional("debug"): Use(boolean),
        Optional("log_level"): log_levels,
        Optional("cache_dir"): str,
        Optional("multiprocessing"): {
            Optional("context"): multiprocessing_contexts,
            Optional("max_tasks_per_child"): positive_int,
        },
        Optional("timeout"): {Optional(str): Use(time_in_seconds)},
        Optional("polling_frequency"): {
            Optional("testcase"): Use(time_in_seconds),
        },
        Optional("plugins"): list_of_str,
    }
)
environment_schema = Schema(
    {
        Optional("set"): vardict,
        Optional("unset"): list_of_str,
        Optional("prepend-path"): vardict,
        Optional("append-path"): vardict,
    }
)
plugin_schema = Schema({str: dict}, ignore_extra_keys=True)
user_schema = Schema({}, ignore_extra_keys=True)

testpaths_schema = Schema({"testpaths": [{"root": str, "paths": list_of_str}]})

# --- Resource pool schemas
resource_spec_schema = Schema(
    {str: [{"id": Use(str), Optional("slots", default=1): Or(int, float)}]}
)
resource_pool_schema = Schema(
    {
        Optional("additional_properties"): dict,
        "resources": resource_spec_schema,
    }
)
