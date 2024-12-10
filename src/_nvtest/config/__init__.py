from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator

from .factory import Config
from .factory import ResourcePool  # noqa: F401
from .factory import ResourceUnavailable  # noqa: F401
from .factory import ResourceUnsatisfiable  # noqa: F401

if TYPE_CHECKING:
    _config = Config.factory()
    machine = _config.machine
    batch = _config.batch
    system = _config.system
    session = _config.session
    test = _config.test
    build = _config.build
    options = _config.options
    resource_pool = _config.resource_pool
    cache_dir = _config.cache_dir
    config_dir = _config.config_dir
    debug = _config.debug
    getoption = _config.getoption
    variables = _config.variables
    invocation_dir = _config.invocation_dir
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
