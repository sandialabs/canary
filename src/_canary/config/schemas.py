# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import typing

from schema import And
from schema import Optional
from schema import Or
from schema import Regex
from schema import Schema
from schema import SchemaError
from schema import Use

from ..util.time import time_in_seconds


def list_of_str(arg: typing.Any) -> bool:
    return isinstance(arg, list) and all([isinstance(_, str) for _ in arg])


def list_of_int(arg: typing.Any) -> bool:
    return isinstance(arg, list) and all([isinstance(_, int) for _ in arg])


optional_dict = Or(dict, None)  # type: ignore
optional_str = Or(str, None)  # type: ignore


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


def log_level_name(arg: typing.Any) -> str:
    logging_levels = ("TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    if isinstance(arg, str):
        level_name = arg.upper()
        if level_name not in logging_levels:
            s = ", ".join(logging_levels)
            raise SchemaError(
                f"Wrong log level {level_name!r}, choose from {', '.join(logging_levels)}"
            )
        return level_name
    raise SchemaError(f"Wrong log level {arg!r}, choose from {', '.join(logging_levels)}")


def multiprocessing_contexts(arg: typing.Any) -> bool:
    if not isinstance(arg, str):
        return False
    elif arg not in ("fork", "spawn"):
        return False
    return True


def boolean(arg: typing.Any) -> bool:
    if isinstance(arg, str):
        return arg.lower() not in ("0", "off", "false", "no")
    return bool(arg)


positive_int = And(int, lambda x: x > 0)  # type: ignore
nonnegative_int = And(int, lambda x: x >= 0)  # type: ignore

any_schema = Schema({}, ignore_extra_keys=True)
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
        Optional("log_level"): Use(log_level_name),
        Optional("cache_dir"): str,
        Optional("view"): Or(bool, str, None),
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

testpaths_schema = Schema({"testpaths": [{"root": str, "paths": list_of_str}]})


class EnvarSchema(Schema):
    def validate(self, data, is_root_eval=True):
        data = super().validate(data, is_root_eval=False)
        if is_root_eval:
            validated = {}
            config = validated.setdefault("config", {})
            for key, val in data.items():
                name = key[7:].lower()
                if name.startswith(("timeout_", "multiprocessing_")):
                    root, _, leaf = name.partition("_")
                    config.setdefault(root, {})[leaf] = val
                elif name.endswith("_polling_frequency"):
                    leaf, _, root = name.partition("_")
                    config.setdefault(root, {})[leaf] = val
                else:
                    config[name] = val
            return validated
        return data


environment_variable_schema = EnvarSchema(
    {
        Optional("CANARY_DEBUG"): Use(boolean),
        Optional("CANARY_LOG_LEVEL"): Use(log_level_name),
        Optional("CANARY_CACHE_DIR"): Use(str),
        Optional("CANARY_PLUGINS"): Use(lambda x: [_.strip() for _ in x.split(",") if _.split()]),
        Optional("CANARY_MULTIPROCESSING_CONTEXT"): multiprocessing_contexts,
        Optional("CANARY_MULTIPROCESSING_MAX_TASKS_PER_CHILD"): positive_int,
        Optional(Regex("CANARY_TIMEOUT_w+")): Use(time_in_seconds),
        Optional("CANARY_TESTCASE_POLLING_FREQUENCY"): Use(time_in_seconds),
    },
    ignore_extra_keys=True,
)
