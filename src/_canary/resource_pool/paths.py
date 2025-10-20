import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PoolPaths:
    prefix: Path
    socket_path: Path
    log_path: Path


def get_resource_pool_home() -> Path:
    """
    Determine the home directory for the resource pool.

    - If CANARY_RESOURCE_POOL_HOME is set in env, use it
    - Otherwise create a temp directory
    """
    if var := os.getenv("CANARY_RESOURCE_POOL_HOME"):
        pool_home = Path(var).expanduser().resolve()
    else:
        pool_home = Path(tempfile.gettempdir()) / "canary/rpool"
    pool_home.mkdir(parents=True, exist_ok=True)
    os.environ["CANARY_RESOURCE_POOL_HOME"] = str(pool_home)
    return pool_home


def get_resource_pool_paths() -> PoolPaths:
    prefix = get_resource_pool_home()
    return PoolPaths(prefix=prefix, socket_path=prefix / "pool.sock", log_path=prefix / "pool.log")
