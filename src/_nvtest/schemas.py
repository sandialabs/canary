from typing import Any

from .util.schema import Optional
from .util.schema import Schema


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


config_schema = Schema(
    {
        "config": {
            Optional("debug"): bool,
            Optional("log_level"): int,
            Optional("test_files"): str,
        }
    }
)
machine_schema = Schema(
    {
        "machine": {
            Optional("sockets_per_node"): int,
            Optional("cores_per_socket"): int,
            Optional("cpu_count"): int,
        },
    }
)
python_schema = Schema(
    {"python": {"executable": str, "version": str, "version_info": list}}
)
variables_schema = Schema({"variables": vardict})
testpaths_schema = Schema({"testpaths": [{"root": str, "paths": list_of_str}]})

any_schema = Schema({}, ignore_extra_keys=True)
