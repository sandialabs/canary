from typing import Any

from ..util.schema import Optional
from ..util.schema import Schema


def list_of_str(arg: Any) -> bool:
    return isinstance(arg, list) and all([isinstance(_, str) for _ in arg])


def tree_struct(arg: Any) -> bool:
    return isinstance(arg, dict) and all([list_of_str(v) for _, v in arg.items()])


config_schema = Schema(
    {
        "nvtest": {
            Optional("debug"): bool,
            Optional("log_level"): int,
            Optional("variables"): {str: str},
            Optional("config"): {
                Optional("debug"): bool,
                Optional("log_level"): int,
                Optional("user_cfg_file"): str,
            },
            Optional("machine"): {
                Optional("sockets_per_node"): int,
                Optional("cores_per_socket"): int,
                Optional("cpu_count"): int,
            },
        },
    },
    ignore_extra_keys=True,
)


testpaths_schema = Schema({"testpaths": [{"root": str, "paths": list_of_str}]})
