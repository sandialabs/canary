# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator

from .config import Config
from .rpool import ResourcePool  # noqa: F401
from .rpool import ResourceUnavailable  # noqa: F401
from .rpool import ResourceUnsatisfiable  # noqa: F401

if TYPE_CHECKING:
    _config = Config.factory()
    batch = _config.batch
    system = _config.system
    session = _config.session
    backend = _config.backend
    test = _config.test
    build = _config.build
    null = _config.null
    options = _config.options
    resource_pool = _config.resource_pool
    plugin_manager = _config.plugin_manager
    config_dir = _config.config_dir
    cache_dir = _config.cache_dir
    debug = _config.debug
    multiprocessing_context = _config.multiprocessing_context
    getoption = _config.getoption
    environment = _config.environment
    invocation_dir = _config.invocation_dir
    working_dir = _config.working_dir
    set_main_options = _config.set_main_options
    describe = _config.describe
    config_file = _config.config_file
    save = _config.save
    snapshot = _config.snapshot
else:
    # allow config to be lazily loaded
    _config: Config | None = None

    def __getattr__(name: str) -> Any:
        global _config
        if _config is None:
            _config = Config.factory()
        return getattr(_config, name)


@contextmanager
def override() -> Generator[None, None, None]:
    global _config
    save_config = _config
    try:
        _config = Config.factory()
        yield
    finally:
        _config = save_config
