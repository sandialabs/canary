# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import typing

from schema import And
from schema import Optional
from schema import Or
from schema import Regex
from schema import Schema
from schema import SchemaError
from schema import Use

from ..util.time import time_in_seconds


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


def boolean(arg: typing.Any) -> bool:
    if isinstance(arg, str):
        return arg.lower() not in ("0", "off", "false", "no")
    return bool(arg)


positive_int = And(int, lambda x: x > 0)  # type: ignore
nonnegative_int = And(int, lambda x: x >= 0)  # type: ignore
optional_str = Or(str, None)  # type: ignore

any_schema = Schema({Optional(str): object}, ignore_extra_keys=True)

environment_schema = Schema(
    {
        Optional("set"): vardict,
        Optional("unset"): [str],
        Optional("prepend-path"): vardict,
        Optional("append-path"): vardict,
    }
)


default_view = {"name": "TestResults", "mode": "symlink", "when": "always", "only": "all"}
view_choices = {
    "mode": {"symlink", "hardlink", "copy"},
    "when": {"on_success", "on_failure", "always", "never"},
    "only": {"failed", "passed", "not_pass", "all"},
}


def validate_view(section: str) -> typing.Callable[[str], bool]:
    def inner(arg: str) -> bool:
        return arg in view_choices[section]

    return inner


workspace_schema = Schema(
    {
        Optional("view", default=default_view): {
            Optional("name", default=default_view["name"]): And(str, lambda s: os.pathsep not in s),
            Optional("mode", default=default_view["mode"]): And(str, validate_view("mode")),
            Optional("when", default=default_view["when"]): And(str, validate_view("when")),
            Optional("only", default=default_view["only"]): And(str, validate_view("only")),
        }
    }
)

run_schema = Schema(
    {Optional("default_tag"): str, Optional("timeout"): {Optional(str): Use(time_in_seconds)}}
)


config_schema = Schema(
    {
        Optional("debug"): Use(boolean),
        Optional("log_level"): Use(log_level_name),
        Optional("workspace"): workspace_schema,
        Optional("plugins"): [str],
        Optional("environment"): environment_schema,
        Optional("scratch"): any_schema,
        Optional("run"): run_schema,
        Optional("system"): any_schema,
        Optional("aliases"): {str: str},
    },
    ignore_extra_keys=True,
)
testpaths_schema = Schema({"testpaths": [{"root": str, "paths": [str]}]})


class EnvarSchema(Schema):
    def validate(self, data: typing.Any, **kwargs: typing.Any):
        is_root_eval = kwargs.pop("is_root_eval", True)
        kwargs["is_root_eval"] = False
        data = super().validate(data, **kwargs)
        if is_root_eval:
            validated: dict[str, typing.Any] = {}
            for key, val in data.items():
                name = key[7:].lower()
                if name.startswith(("timeout_",)):
                    root, _, leaf = name.partition("_")
                    validated.setdefault(root, {})[leaf] = val
                elif name.endswith("_polling_frequency"):
                    leaf, _, root = name.partition("_")
                    validated.setdefault(root, {})[leaf] = val
                else:
                    validated[name] = val
            return validated
        return data


environment_variable_schema = EnvarSchema(
    {
        Optional("CANARY_DEBUG"): Use(boolean),
        Optional("CANARY_LOG_LEVEL"): Use(log_level_name),
        Optional("CANARY_PLUGINS"): Use(lambda x: [_.strip() for _ in x.split(",") if _.split()]),
        Optional(Regex("CANARY_TIMEOUT_w+")): Use(time_in_seconds),
        Optional("CANARY_TESTCASE_POLLING_FREQUENCY"): Use(time_in_seconds),
    },
    ignore_extra_keys=True,
)

# -------------------------------------------------------------------------
# Query capability / skill schemas
# -------------------------------------------------------------------------


def _non_empty_string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"expected str, got {type(value).__name__}")
    value = value.strip()
    if not value:
        raise ValueError("expected non-empty string")
    return value


def _query_namespace(value: object) -> str:
    """Validate a query namespace component such as an extension name.

    Extension namespaces are used as query path components under ``ext``.
    Keep the character set conservative so selectors such as
    ``ext.pyt.overview`` remain unambiguous.
    """
    text = _non_empty_string(value)
    if not text.replace("_", "").replace("-", "").isalnum():
        raise ValueError(
            "query namespace must contain only letters, digits, underscores, "
            f"and hyphens; got {value!r}"
        )
    return text


json_scalar_schema = Or(str, int, float, bool, type(None))

# Recursive JSON-like data.  The schema package does not make recursive schemas
# especially elegant, so for capability payloads we validate only that the root
# payload is a dict.  Individual nested values remain JSON-compatible by
# construction because they are loaded from JSON or returned by trusted plugins.
query_payload_schema = dict


skill_schema = Schema(
    {
        "name": And(str, Use(_non_empty_string)),
        "description": And(str, Use(_non_empty_string)),
        "body": str,
        Optional(str): object,
    },
    ignore_extra_keys=False,
)


skills_payload_schema = Schema({str: skill_schema})


query_document_base_schema = {"schema_version": And(str, Use(_non_empty_string))}


core_capabilities_schema = Schema(
    {**query_document_base_schema, "capabilities": query_payload_schema}, ignore_extra_keys=False
)


extension_capabilities_schema = Schema(
    {
        **query_document_base_schema,
        "extension": And(str, Use(_query_namespace)),
        "capabilities": query_payload_schema,
    },
    ignore_extra_keys=False,
)


core_skills_schema = Schema(
    {**query_document_base_schema, "skills": skills_payload_schema}, ignore_extra_keys=False
)


extension_skills_schema = Schema(
    {
        **query_document_base_schema,
        "extension": And(str, Use(_query_namespace)),
        "skills": skills_payload_schema,
    },
    ignore_extra_keys=False,
)
