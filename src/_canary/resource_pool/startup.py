import atexit
import logging
import os
import platform
import socket
import tempfile
import time
from multiprocessing import Process
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

import uvicorn

from ..util.logging import get_logger
from .rpool import ResourcePool
from .schemas import resource_pool_schema
from .server_app import create_pool_server_app_starlette

if TYPE_CHECKING:
    from ..config import Config

logger = get_logger(__name__)


def setup_logging(logfile: Path) -> None:
    """Configure both request and uvicorn logs to a single file."""
    logfile.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(logfile, mode="w")],
    )
    # Redirect uvicorn logs to same handlers
    logging.getLogger("uvicorn").handlers = logging.getLogger().handlers
    logging.getLogger("uvicorn.access").handlers = logging.getLogger().handlers


def make_resource_pool(config: "Config"):
    resources: dict[str, list[dict[str, Any]]] = {}
    config.pluginmanager.hook.canary_fill_resource_pool(config=config, resources=resources)
    pool = resource_pool_schema.validate({"resources": resources, "additional_properties": {}})
    return ResourcePool(pool)


def run_resource_pool_server(pool: ResourcePool, kwargs: dict) -> None:
    app = create_pool_server_app_starlette(pool)
    uvicorn.run(app, log_config=None, access_log=True, **kwargs)


def wait_for_socket_to_connect(socketfile: Path, timeout: float = 1.5) -> None:
    start = time.monotonic()
    while (time.monotonic() - start) <= timeout:
        if socketfile.exists():
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(str(socketfile))
                s.close()
                break
            except ConnectionRefusedError as e:
                pass
        time.sleep(0.05)
    else:
        raise TimeoutError(f"Resource pool server did not start within {timeout:.1f} s.")


def wait_for_port_to_connect(host: str, port: int, timeout: float = 1.5) -> None:
    start = time.monotonic()
    while (time.monotonic() - start) <= timeout:
        try:
            with socket.create_connection((host, port), timeout=0.05):
                break
        except OSError:
            time.sleep(0.05)
    else:
        raise TimeoutError(f"Resource pool server did not start within {timeout:.1f} s.")


def start_resource_pool_server(config: "Config") -> None:
    """Start the local resource pool server in a subprocess and return."""
    kwargs: dict[str, Any] = {}
    if var := os.getenv("CANARY_RESOURCE_POOL_ADDR"):
        protocol, _, address = var.partition(":")
        if protocol == "uds":
            path = Path(address)
            kwargs["uds"] = str(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                path.unlink()
        elif protocol == "tcp":
            host, port = address.split(":")
            kwargs["host"] = host
            kwargs["port"] = int(port)
        else:
            raise ValueError("Expected CANARY_RESOURCE_POOL_ADDR protocol to be uds or tcp")
    elif platform.system() == "Windows":
        kwargs["host"] = "127.0.0.1"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = s.getsockname()[1]
        kwargs["port"] = port
        os.environ["CANARY_RESOURCE_POOL_ADDR"] = f"tcp:127.0.0.1:{port}"
    else:
        path = Path(tempfile.gettempdir()) / "canary/0/pool.socket"
        path.parent.mkdir(parents=True, exist_ok=True)
        kwargs["uds"] = str(path)
        os.environ["CANARY_RESOURCE_POOL_ADDR"] = f"uds:{str(path)}"

    logfile: Path
    if var := os.getenv("CANARY_RESOURCE_POOL_HOME"):
        logfile = Path(var) / "pool.log"
    else:
        if "uds" in kwargs:
            logfile = Path(kwargs["uds"]).with_stem("pool.log")
        else:
            logfile = Path(tempfile.gettempdir()) / "canary/0/pool.log"
        os.environ["CANARY_RESOURCE_POOL_HOME"] = str(logfile.parent)

    assert "CANARY_RESOURCE_POOL_HOME" in os.environ
    assert "CANARY_RESOURCE_POOL_ADDR" in os.environ

    setup_logging(logfile)
    pool = make_resource_pool(config)
    proc = Process(target=run_resource_pool_server, args=(pool, kwargs), daemon=True)
    proc.start()
    if "port" in kwargs:
        wait_for_port_to_connect(kwargs["host"], kwargs["port"])
    else:
        wait_for_socket_to_connect(Path(kwargs["uds"]))
    # Write PID for optional monitoring
    (logfile.parent / "pool.pid").write_text(str(proc.pid))

    # Ensure socket cleanup and process termination on exit
    def cleanup():
        logger.debug("Shutting down resource pool server")
        if p := kwargs.get("uds"):
            socketfile = Path(p)
            if socketfile.exists():
                socketfile.unlink()
        proc.terminate()
        proc.join(timeout=1)

    atexit.register(cleanup)

    return
