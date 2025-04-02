# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import typing

from ..third_party.schema import And
from ..third_party.schema import Forbidden
from ..third_party.schema import Optional
from ..third_party.schema import Or
from ..third_party.schema import Regex
from ..third_party.schema import Schema
from ..third_party.schema import SchemaError
from ..third_party.schema import SchemaMissingKeyError
from ..third_party.schema import Use
from ..util.rprobe import cpu_count
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


config_schema = Schema(
    {
        "config": {
            Optional("debug"): Use(boolean),
            Optional("log_level"): log_levels,
            Optional("cache_dir"): str,
            Optional("multiprocessing_context"): multiprocessing_contexts,
        }
    }
)


batch_schema = Schema(
    {
        "batch": {
            Optional("duration"): Use(time_in_seconds),
            Optional("default_options"): list_of_str,
        }
    }
)

test_schema = Schema({"test": {"timeout": {Optional(str): Use(time_in_seconds)}}})

machine_schema = Schema({"machine": {Optional("cpu_count"): Use(int)}})
python_schema = Schema({"python": {"executable": str, "version": str, "version_info": list}})
testpaths_schema = Schema({"testpaths": [{"root": str, "paths": list_of_str}]})
environment_schema = Schema(
    {
        "environment": {
            Optional("set"): vardict,
            Optional("unset"): list_of_str,
            Optional("prepend-path"): vardict,
            Optional("append-path"): vardict,
        }
    }
)

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


positive_int = And(int, lambda x: x > 0)
nonnegative_int = And(int, lambda x: x >= 0)
id_list = Schema([{"id": Use(str), Optional("slots", default=1): Or(int, float)}])


ctest_resource_pool_schema = Schema(
    {
        "local": {
            Optional(Regex("^[a-z_][a-z0-9_]*?(?<!_per_node)$")): id_list,
        }
    }
)


local_resource_pool_schema = Schema(
    {
        "resource_pool": {
            # The local schema does not allow nodes
            Forbidden("nodes"): object,
            Optional("cpus", default=cpu_count()): positive_int,
            # local schema disallows *_per_node
            Optional(Regex("^[a-z_][a-z0-9_]*?(?<!_per_node)$")): nonnegative_int,
        }
    }
)


uniform_resource_pool_schema = Schema(
    {
        "resource_pool": {
            "nodes": positive_int,
            "cpus_per_node": positive_int,
            Optional(Regex("^[a-z_][a-z0-9_]*_per_node")): nonnegative_int,
        }
    }
)


heterogeneous_resource_pool_schema = Schema(
    {
        "resource_pool": [
            {
                "id": Use(str),
                "cpus": id_list,
                # local schema disallows *_per_node
                Optional(Regex("^[a-z_][a-z0-9_]*?(?<!_per_node)$")): id_list,
            }
        ]
    }
)


class ResourceSchema(Schema):
    def __init__(self):
        self.schemas = {
            "ctest": ctest_resource_pool_schema,
            "local": local_resource_pool_schema,
            "uniform": uniform_resource_pool_schema,
            "heterogeneous": heterogeneous_resource_pool_schema,
        }

    def validate(self, data):
        if not isinstance(data, dict):
            raise SchemaError("Expected resource_pool to be a dict")
        if "local" in data:
            validated = self.schemas["ctest"].validate(data)
            if "cpus" not in validated["local"]:
                validated["local"]["cpus"] = self.uniform_pool_object(cpu_count())
            return {"resource_pool": [{"id": "0"} | validated["local"]]}
        if "resource_pool" not in data:
            raise SchemaMissingKeyError("Missing key: 'resource_pool'", self._error)
        resource_pool = data["resource_pool"]
        if isinstance(resource_pool, dict) and "nodes" in resource_pool:
            # uniform resource pool
            validated = self.schemas["uniform"].validate(data)
            rp = []
            for i in range(validated["resource_pool"].pop("nodes")):
                x = {"id": str(i)}
                for name, count in validated["resource_pool"].items():
                    x[name[:-9]] = self.uniform_pool_object(count)
                rp.append(x)
            return {"resource_pool": rp}
        if isinstance(resource_pool, dict):
            # uniform resource pool, single node
            validated = self.schemas["local"].validate(data)
            if "cpus" not in validated["resource_pool"]:
                validated["resource_pool"]["cpus"] = cpu_count()
            rp = {"id": "0"}
            for name, count in validated["resource_pool"].items():
                rp[name] = self.uniform_pool_object(count)
            return {"resource_pool": [rp]}
        if isinstance(resource_pool, list):
            validated = self.schemas["heterogeneous"].validate(data)
            return validated
        raise SchemaError("Unrecognized resource_pool layout")

    @staticmethod
    def uniform_pool_object(n: int) -> list[dict[str, typing.Any]]:
        if n < 0:
            raise ValueError(f"expected pool object count > 0, got {n=}")
        return [{"id": str(i), "slots": 1} for i in range(n)]


resource_schema = ResourceSchema()
