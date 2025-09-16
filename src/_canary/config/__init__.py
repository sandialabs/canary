# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator

from .config import Config
from .config import ConfigScope  # noqa: F401
from .config import get_scope_filename  # noqa: F401
from .rpool import ResourcePool  # noqa: F401
from .rpool import ResourceUnavailable  # noqa: F401

if TYPE_CHECKING:
    _config = Config()

    add = _config.add
    get = _config.get
    set = _config.set
    getstate = _config.getstate

    pluginmanager = _config.pluginmanager
    invocation_dir = _config.invocation_dir
    working_dir = _config.working_dir
    resource_pool = _config.resource_pool
    getoption = _config.getoption
    set_main_options = _config.set_main_options
    cache_dir = _config.cache_dir
    options = _config.options
    dump_snapshot = _config.dump_snapshot
    ensure_loaded = lambda: None
    load_snapshot = _config.load_snapshot
    archive = _config.archive
    temporary_scope = _config.temporary_scope

else:
    # allow config to be lazily loaded
    _config: Config | None = None

    def ensure_loaded() -> None:
        global _config
        if _config is None:
            _config = Config()

    def __getattr__(name: str) -> Any:
        global _config
        if _config is None:
            _config = Config()
        if name == "debug":
            return _config.get("config:debug")
        return getattr(_config, name)


@contextmanager
def override() -> Generator[Config, None, None]:
    global _config
    save_config = _config
    try:
        _config = Config()
        yield _config
    finally:
        _config = save_config
