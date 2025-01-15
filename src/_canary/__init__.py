import importlib
import importlib.resources as ir

from .error import TestDiffed  # noqa: F401
from .error import TestFailed  # noqa: F401
from .error import TestSkipped  # noqa: F401

# Constant that's True when file scanning, but False here.
FILE_SCANNING = False


def _load_builtin_plugins() -> None:
    from .util import logging

    path = ir.files("_canary").joinpath("plugins")  # type: ignore
    logging.debug(f"Loading builtin plugins from {path}")
    if path.exists():  # type: ignore
        importlib.import_module(f".{path.name}", "_canary")


_load_builtin_plugins()
