import functools
import glob
import importlib.resources as ir
import os
import sys
from argparse import Namespace
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Generator
from typing import Optional
from typing import Type

from .database import Database
from .util import logging
from .util.entry_points import get_entry_points
from .util.serialization import deserialize
from .util.serialization import serialize
from .util.singleton import Singleton

if TYPE_CHECKING:
    from .test.generator import TestGenerator


class PluginHook:
    def __init__(self, func: Callable, **kwds: str) -> None:
        self.func = func
        self.specname = f"{func.__name__}_impl"  # type: ignore
        self.attrs = dict(kwds)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def get_attribute(self, name: str) -> Optional[str]:
        return self.attrs.get(name)


class Manager:
    def __init__(self) -> None:
        self._plugins: dict[str, dict[str, list[PluginHook]]] = {}
        self._generators: list[Type["TestGenerator"]] = []
        self._args: Optional[Namespace] = None
        self._builtin_loaded = False

    def load_builtin(self, disable: Optional[list[str]] = None) -> None:
        path = ir.files("nvtest").joinpath("plugins")
        disable = disable or []
        logging.debug(f"Loading builtin plugins from {path}")
        if path.exists():  # type: ignore
            for file in path.iterdir():
                if file.name.startswith("nvtest_"):
                    name = os.path.splitext(file.name[7:])[0]
                    if name in disable:
                        logging.debug(f"Skipping disabled plugin {name}")
                        continue
                    logging.debug(f"Loading {file.name} builtin plugin")
                    self.load_from_file(str(file))
        self._builtin_loaded = True

    @property
    def args(self) -> Namespace:
        if self._args is None:
            return Namespace()
        return self._args

    def set_args(self, arg: Namespace) -> None:
        self._args = arg

    def register_test_generator(self, obj: Type["TestGenerator"]) -> None:
        self._generators.append(obj)

    def register(self, func: Callable, scope: str, stage: str, **kwds: str) -> None:
        name = func.__name__
        logging.debug(f"Registering plugin {name}::{scope}::{stage}")
        err_msg = f"register() got unexpected stage '{scope}::{stage}'"
        if stage == "teardown":
            logging.warning(f"plugin::{name}: prefer 'finish' to 'teardown'")
            stage = "finish"
        if scope == "main":
            if stage not in ("setup",):
                raise TypeError(err_msg)
        elif scope == "report":
            if stage not in ("setup", "create"):
                raise TypeError(err_msg)
            if scope in ("setup", "create") and "type" not in kwds:
                raise TypeError("report::setup plugin must define 'type'")
        elif scope == "session":
            if stage not in ("discovery", "setup", "finish"):
                raise TypeError(err_msg)
        elif scope == "test":
            if stage not in ("discovery", "setup", "pre:baseline", "pre:run", "finish"):
                raise TypeError(err_msg)
        else:
            raise TypeError(f"register() got unexpected scope {scope!r}")

        scope_plugins = self._plugins.setdefault(scope, {})
        stage_plugins = scope_plugins.setdefault(stage, [])
        hook = PluginHook(func, **kwds)
        stage_plugins.append(hook)

    def plugins(self, scope: str, stage: str) -> Generator[PluginHook, None, None]:
        for hook in self._plugins.get(scope, {}).get(stage, []):
            yield hook

    def get_plugin(self, scope: str, stage: str, name: str) -> Optional[PluginHook]:
        if scope in self._plugins and stage in self._plugins[scope]:
            specname = f"{name}_impl"
            for hook in self._plugins[scope][stage]:
                if hook.specname == specname:  # type: ignore
                    return hook
        return None

    def load_from_directory(self, path: str) -> None:
        for file in glob.glob(os.path.join(path, "nvtest_*.py")):
            self.load_from_file(file)

    def load_from_file(self, file: str) -> None:
        basename = os.path.splitext(os.path.basename(file))[0]
        name = f"nvtest.plugins.{basename}"
        # importing the module will load the plugins
        load_module_from_file(name, file)

    def load_from_entry_points(self, disable: Optional[list[str]] = None):
        disable = disable or []
        entry_points = get_entry_points(group="nvtest.plugin")
        if entry_points:
            for entry_point in entry_points:
                if entry_point.name in disable or entry_point.module in disable:
                    logging.debug(f"Skipping disabled plugin {entry_point.name}")
                    continue
                logging.debug(f"Loading the {entry_point.name} plugin from {entry_point.module}")
                entry_point.load()


def load_module_from_file(module_name: str, module_path: str):
    """Loads a python module from the path of the corresponding file.

    If the module is already in ``sys.modules`` it will be returned as
    is and not reloaded.

    Args:
        module_name (str): namespace where the python module will be loaded,
            e.g. ``foo.bar``
        module_path (str): path of the python file containing the module

    Returns:
        A valid module object

    Raises:
        ImportError: when the module can't be loaded
        FileNotFoundError: when module_path doesn't exist
    """
    import importlib.util

    if module_name in sys.modules:
        return sys.modules[module_name]

    # This recipe is adapted from https://stackoverflow.com/a/67692/771663

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None:
        raise ValueError(f"Could not find spec for plugin {module_path}")
    module = importlib.util.module_from_spec(spec)
    if spec is None:
        raise ImportError(module_name)
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
    if os.getenv("NVTEST_LEVEL") == "0" and "NVTEST_SESSION_CONFIG_DIR" in os.environ:
        # Setting up test cases and several other operations are done in a
        # multiprocessing Pool so we reload the configuration that existed when that pool
        # was created
        db = Database(os.environ["NVTEST_SESSION_CONFIG_DIR"], mode="r")
        if db.exists("plugin"):
            return db.load_binary("plugin")
    return Manager()


_manager = Singleton(Manager)


def set_args(args: Namespace) -> None:
    _manager.set_args(args)


def plugins(scope: str, stage: str) -> Generator[PluginHook, None, None]:
    if not _manager._builtin_loaded:
        _manager.load_builtin()
    return _manager.plugins(scope, stage)


def get(scope: str, stage: str, name: str) -> Optional[PluginHook]:
    if not _manager._builtin_loaded:
        _manager.load_builtin()
    return _manager.get(scope, stage, name)


def register(*, scope: str, stage: str, **kwds: str):
    """Decorator to register a callback"""

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            return func(*args, **kwargs)

        _manager.register(func, scope, stage, **kwds)
        return wrapper

    return decorator


def test_generator(hook: Callable) -> None:
    _manager.register_test_generator(hook)


def test_generators() -> list[Type["TestGenerator"]]:
    if not _manager._builtin_loaded:
        _manager.load_builtin()
    return _manager._generators


def load_builtin_plugins(disable: Optional[list[str]] = None) -> None:
    _manager.load_builtin(disable=disable)


def load_from_entry_points(disable: Optional[list[str]] = None) -> None:
    logging.debug("Loading plugins from entry points")
    _manager.load_from_entry_points(disable=disable)


def load_from_directory(path: str) -> None:
    logging.debug(f"Loading plugins from {path}")
    _manager.load_from_directory(path)


def dumps() -> str:
    return serialize(_manager._instance)


def loads(string: str) -> Manager:
    return deserialize(string)
