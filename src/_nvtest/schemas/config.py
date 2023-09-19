from typing import Any

from ..util.schema import Optional
from ..util.schema import Or
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
            },
            Optional("machine"): {
                Optional("sockets_per_node"): int,
                Optional("cores_per_socket"): int,
                Optional("cpu_count"): int,
            },
            Optional("run-tests"): {
                Optional("search_paths"): list_of_str,
                Optional("keyword_expr"): str,
                Optional("timeout"): Or(int, float, str),
                Optional("workdir"): str,
                Optional("wipe"): bool,
                Optional("max_workers"): int,
            },
        },
    },
)


testpaths_schema = Schema({"testpaths": Or(list_of_str, tree_struct)})
