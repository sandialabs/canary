import functools
import glob
import importlib
import importlib.resources as ir
import inspect
import json
import os
import sys
from pathlib import Path
from types import new_class
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Generator
from typing import Type

from .util import logging
from .util.entry_points import get_entry_points
from .util.singleton import Singleton

if TYPE_CHECKING:
    from .command.base import Command
    from .config.argparsing import Parser
    from .finder import Finder
    from .generator import AbstractTestGenerator
    from .session import Session
    from .test.case import TestCase


class PluginHook:
    """Defines hooks into the nvtest execution.  User's can extend nvtest by subclassing this class
    or decorating a function with ``@register(scope=..., stage=...)``

    """

    REGISTRY: set[Type["PluginHook"]] = set()

    def __init_subclass__(cls) -> None:
        PluginHook.REGISTRY.add(cls)

    @staticmethod
    def main_setup(parser: "Parser") -> None:
        """Call user plugin before arguments are parsed"""

    @staticmethod
    def session_initialize(session: "Session") -> None:
        """Call user plugin during session initialization"""

    @staticmethod
    def session_discovery(finder: "Finder") -> None:
        """Call user plugin during the discovery stage, before search paths passed on the command
        line are searched

        """

    @staticmethod
    def session_finish(session: "Session") -> None:
        """Call user plugin at the end of the session"""

    @staticmethod
    def test_discovery(case: "TestCase") -> None:
        """Call user plugin during the test discovery stage"""

    @staticmethod
    def test_setup(case: "TestCase") -> None:
        """Call user plugin at the end of the test setup stage"""

    @staticmethod
    def test_before_run(case: "TestCase", *, stage: str | None = None) -> None:
        """Call user plugin immediately before running the test"""

    @staticmethod
    def test_after_launch(case: "TestCase") -> None:
        """Call user plugin immediately after the test is launched"""

    @staticmethod
    def test_after_run(case: "TestCase") -> None:
        """Call user plugin after the test has ran"""


class Manager:
    def __init__(self) -> None:
        self.files: set[str] = set()
        self.entry_points_loaded: bool = False
        self.disabled_entry_points: list[str] = []

    def register(self, func: Callable, *, scope: str, stage: str) -> None:
        name = func.__name__
        logging.debug(f"Registering plugin {name}::{scope}::{stage}")
        err_msg = f"register() got unexpected stage '{scope}::{stage}'"

        method_name: str
        match [scope, stage]:
            case ["main", "setup"]:
                method_name = "main_setup"
            case ["session", "discovery"]:
                method_name = "session_discovery"
            case ["session", "initialize"] | ["session", "setup"]:
                method_name = "session_initialize"
            case ["session", "finish"] | ["session", "teardown"] | ["session", "after_run"]:
                method_name = "session_finish"
            case ["test", "discovery"]:
                method_name = "test_discovery"
            case ["test", "setup"]:
                method_name = "test_setup"
            case ["test", "before_run"] | ["test", "prepare"] | ["test", "prelaunch"]:
                method_name = "test_before_run"
            case ["test", "after_launch"]:
                method_name = "test_after_launch"
            case ["test", "after_run"] | ["test", "finish"] | ["test", "teardown"]:
                method_name = "test_after_run"
            case _:
                raise TypeError(err_msg)

        module = func.__module__
        namespace = module.split(".")[0]
        attributes = {
            method_name: staticmethod(func),
            "namespace": namespace,
            "name": f"{module}.{name}",
            "file": inspect.getfile(func),
        }
        plugin_class_name = f"{module.replace('.', '_')}_{name}"

        # By simply creating the class, the plugin is registered with the base class
        t = new_class(plugin_class_name, (PluginHook,), exec_body=lambda ns: ns.update(attributes))

    def iterplugins(self) -> Generator[Type[PluginHook], None, None]:
        if not self.entry_points_loaded:
            self.load_from_entry_points()
        for hook in PluginHook.REGISTRY:
            yield hook

    def getstate(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "files": list(self.files),
            "entry_points_loaded": self.entry_points_loaded,
            "disabled_entry_points": self.disabled_entry_points,
        }
        return state

    def setstate(self, state: dict[str, Any]) -> None:
        for file in state["files"]:
            self.load_from_file(file)
        if state["entry_points_loaded"]:
            self.load_from_entry_points(disable=state["disabled_entry_points"])

    def load_builtins(self) -> None:
        for resource in ir.files("_nvtest.plugins").iterdir():
            if resource.name.startswith("nvtest_"):
                importlib.import_module(f".{resource.name}", "_nvtest.plugins")

    def load_from_env(self) -> None:
        if "NVTEST_PLUGINS" in os.environ:
            for path in os.environ["NVTEST_PLUGINS"].split(":"):
                if os.path.exists(path):
                    self.load_from_path(path)
                else:
                    logging.warning(f"{path}: plugin path not found")

    def load_from_path(self, path: str) -> None:
        if os.path.isfile(path):
            self.load_from_file(path)
        elif os.path.isdir(path):
            for file in glob.glob(os.path.join(path, "nvtest_*.py")):
                self.load_from_file(file)
        else:
            raise ValueError(f"No such file or directory: {path!r}")

    def load_from_file(self, file: Path | str) -> None:
        file = Path(file)
        if str(file.resolve()) in self.files:
            return
        name = f"_nvtest.plugins.{file.parent.name}.{file.stem}"
        # simply importing the module will load the plugins
        self.files.add(str(file.resolve()))
        load_module_from_file(name, file)

    def load_from_entry_points(self, disable: list[str] | None = None):
        disable = disable or []
        if self.entry_points_loaded:
            return
        entry_points = get_entry_points(group="nvtest.plugin")
        if entry_points:
            for entry_point in entry_points:
                if entry_point.name in disable or entry_point.module in disable:
                    logging.debug(f"Skipping disabled plugin {entry_point.name}")
                    continue
                if entry_point.module.split(".")[0] in disable:
                    logging.debug(f"Skipping disabled plugin {entry_point.name}")
                    continue
                logging.debug(f"Loading the {entry_point.name} plugin from {entry_point.module}")
                entry_point.load()
        self.entry_points_loaded = True
        self.disabled_entry_points.clear()
        self.disabled_entry_points.extend(disable)

    @staticmethod
    def generators() -> Generator[Type["AbstractTestGenerator"], None, None]:
        from .generator import AbstractTestGenerator

        for generator_class in AbstractTestGenerator.REGISTRY:
            yield generator_class

    @staticmethod
    def commands() -> Generator[Type["Command"], None, None]:
        from .command.base import Command

        for command_class in Command.REGISTRY:
            yield command_class


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


def factory() -> Manager:
    manager = Manager()
    manager.load_builtins()
    if os.getenv("NVTEST_LEVEL") == "0" and "NVTEST_WORK_TREE" in os.environ:
        # Setting up test cases and several other operations are done in a
        # multiprocessing Pool so we reload the configuration that existed when that pool
        # was created
        file = os.path.join(os.environ["NVTEST_WORK_TREE"], ".nvtest/objects/plugin")
        if os.path.exists(file):
            state = json.load(open(file))
            manager.setstate(state)
    return manager


_manager = Singleton(factory)


def plugins() -> Generator[Type[PluginHook], None, None]:
    return _manager.iterplugins()


def hooks() -> Generator[Type[PluginHook], None, None]:
    return _manager.iterplugins()


def generators() -> Generator[Type["AbstractTestGenerator"], None, None]:
    return _manager.generators()


def commands() -> Generator[Type["Command"], None, None]:
    return _manager.commands()


def register(*, scope: str, stage: str, **kwds: str):
    """Decorator to register a callback"""

    def decorator(func: Callable):
        _manager.register(func, scope=scope, stage=stage)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            return func(*args, **kwargs)

        return wrapper

    return decorator


def load_from_entry_points(disable: list[str] | None = None) -> None:
    logging.debug("Loading plugins from entry points")
    _manager.load_from_entry_points(disable=disable)


def load_from_path(path: str) -> None:
    logging.debug(f"Loading plugins from {path}")
    _manager.load_from_path(path)


def getstate() -> dict[str, Any]:
    return _manager.getstate()
