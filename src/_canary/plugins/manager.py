import glob
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Type

import pluggy

from ..util import logging
from . import builtin
from . import generators
from . import hookspec
from . import reporters
from . import subcommands
from .types import CanarySubcommand

if TYPE_CHECKING:
    from ..generator import AbstractTestGenerator


class CanaryPluginManager(pluggy.PluginManager):
    def __init__(self, project_name: str):
        super().__init__(project_name)
        self.files: set[str] = set()

    @classmethod
    def factory(cls) -> "CanaryPluginManager":
        self = cls(hookspec.project_name)
        self.add_hookspecs(hookspec)
        for subcommand in subcommands.plugins:
            self.register(subcommand)
        for generator in generators.plugins:
            self.register(generator)
        for p in builtin.plugins:
            self.register(p)
        for p in reporters.plugins:
            self.register(p)
        self.load_setuptools_entrypoints(hookspec.project_name)
        self.load_from_env()
        return self

    def get_subcommands(self) -> list[CanarySubcommand]:
        hook = self.hook.canary_subcommand
        return hook()

    def get_generators(self) -> list[Type["AbstractTestGenerator"]]:
        hook = self.hook.canary_testcase_generator
        return hook()

    def load_from_paths(self, paths: list[str]) -> None:
        disable, dirs = [], []
        for path in paths:
            if path.startswith("no:"):
                disable.append(path[3:])
            elif not os.path.exists(path):
                logging.warning(f"{path}: plugin directory not found")
            else:
                dirs.append(path)
        for dir in dirs:
            path = os.path.abspath(dir)
            self.load_from_path(path)

    def load_from_env(self) -> None:
        if "CANARY_PLUGINS" in os.environ:
            for path in os.environ["CANARY_PLUGINS"].split(":"):
                if os.path.exists(path):
                    self.load_from_path(path)
                else:
                    logging.warning(f"{path}: plugin path not found")

    def load_from_path(self, path: str) -> None:
        if os.path.isfile(path):
            self.load_from_file(path)
        elif os.path.isdir(path):
            for file in glob.glob(os.path.join(path, "canary_*.py")):
                self.load_from_file(file)
        else:
            raise ValueError(f"No such file or directory: {path!r}")

    def load_from_file(self, file: Path | str) -> None:
        file = Path(file)
        name = f"_canary.plugins.{file.parent.name}.{file.stem}"
        # simply importing the module will load the plugins
        m = load_module_from_file(name, file)
        try:
            self.register(m)
            self.files.add(str(file.absolute()))
        except ValueError:
            # plugin already loaded
            pass


def load_module_from_file(name: str, path: Path | str):
    """Loads a python module from the path of the corresponding file.

    If the module is already in ``sys.modules`` it will be returned as
    is and not reloaded.

    Args:
        name: namespace where the python module will be loaded, e.g. ``foo.bar``
        path: path of the python file containing the module

    Returns:
        A valid module object

    Raises:
        ImportError: when the module can't be loaded
        FileNotFoundError: when path doesn't exist
    """
    import importlib.util

    if name in sys.modules:
        return sys.modules[name]

    # This recipe is adapted from https://stackoverflow.com/a/67692/771663

    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None:
        raise ValueError(f"Could not find spec for plugin {path}")
    module = importlib.util.module_from_spec(spec)
    if spec is None:
        raise ImportError(name)
    # The module object needs to exist in sys.modules before the
    # loader executes the module code.
    #
    # See https://docs.python.org/3/reference/import.html#loading
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore
    except BaseException:
        try:
            del sys.modules[spec.name]
        except KeyError:
            pass
        raise
    return module
