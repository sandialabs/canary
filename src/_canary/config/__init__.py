# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import typing
from contextlib import contextmanager

from .config import CONFIG_ENV_FILENAME  # noqa: F401
from .config import Config
from .config import get_scope_filename  # noqa: F401

__all__ = ["Config", "CONFIG_ENV_FILENAME", "get_scope_filename"]


class _resource_pool_attr_error:
    def __getattribute__(self, name):
        import io

        f = io.StringIO()
        f.write(
            "The global canary resource pool has been removed in favor of executor-specific "
            "resource pools.  Properties of the resource pool are accessed through the canary "
            "plugin manager. "
        )
        if name in ("count", "types", "accommodates"):
            repl = f"config.pluginmanger.canary_resource_pool_{name}"
        else:
            repl = f"a plugin call that can return the pool's {name!r} attribute"
        f.write(f"In this case, replace config.resource_pool.{name} with {repl}.")
        raise AttributeError(f.getvalue().strip()) from None


resource_pool = _resource_pool_attr_error()


_config: Config | None = None

if typing.TYPE_CHECKING:
    _config = typing.cast(Config, _config)
    pluginmanager = _config.pluginmanager
    getoption = _config.getoption
    add_section = _config.add_section
    get = _config.get
    set = _config.set
    data = _config.data
    write_new = _config.write_new


def ensure_loaded() -> None:
    global _config
    if _config is None:
        _config = Config.factory()


def load_snapshot(snapshot: dict[str, typing.Any]) -> None:
    global _config
    _config = None
    _config = Config.from_snapshot(snapshot)


def __getattr__(name: str) -> typing.Any:
    global _config
    if _config is None:
        _config = Config.factory()
    return getattr(_config, name)


@contextmanager
def override() -> typing.Generator[Config, None, None]:
    global _config
    save_config = _config
    try:
        _config = Config()
        yield _config
    finally:
        _config = save_config
