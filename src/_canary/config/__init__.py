# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import typing
from contextlib import contextmanager

from .config import CONFIG_ENV_CFG64  # noqa: F401
from .config import CONFIG_ENV_FILENAME  # noqa: F401
from .config import Config
from .config import ConfigError  # noqa: F401
from .config import get_scope_filename  # noqa: F401

__all__ = ["Config", "ConfigError", "CONFIG_ENV_FILENAME", "get_scope_filename"]


_config: Config | None = None

if typing.TYPE_CHECKING:
    _config = typing.cast(Config, _config)
    pluginmanager = _config.pluginmanager
    resource_manager = _config.resource_manager
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


def get_timeout_option(name: str, default: float | None = None) -> float | None:
    ensure_loaded()
    assert _config is not None
    timeouts = _config.getoption("timeout") or {}
    return timeouts.get(name, default)


def timeout_multiplier() -> float:
    ensure_loaded()
    assert _config is not None
    if cli_timeouts := _config.getoption("timeout"):
        if t := cli_timeouts.get("multiplier"):
            return float(t)
    if t := _config.get("run:timeout:multiplier"):
        return float(t)
    return 1.0


def __getattr__(name: str) -> typing.Any:
    global _config
    if _config is None:
        _config = Config.factory()
    return getattr(_config, name)


def is_loaded() -> bool:
    """True if the configuration singleton has been successfully created."""
    return _config is not None


def safe_get(path: str, default: typing.Any = None) -> typing.Any:
    """``get(path)`` that never (re)loads configuration and never raises.

    For use in error handlers: if loading the configuration is what failed,
    calling :func:`get` would try to load it again and raise inside the handler.
    """
    if _config is None:
        return default
    try:
        return _config.get(path, default)
    except Exception:
        return default


@contextmanager
def override() -> typing.Generator[Config, None, None]:
    global _config
    save_config = _config
    try:
        _config = Config()
        yield _config
    finally:
        _config = save_config
