import functools
import glob
import importlib.metadata as im
import os
import sys
from argparse import Namespace
from typing import Any
from typing import Callable
from typing import Generator
from typing import Optional

from .util import tty
from .util.singleton import Singleton


class Manager:
    def __init__(self) -> None:
        self._plugins: dict[str, dict[str, list[Callable]]] = {}
        self._args: Optional[Namespace] = None

    @property
    def args(self) -> Namespace:
        if self._args is None:
            return Namespace()
        return self._args

    def set_args(self, arg: Namespace) -> None:
        self._args = arg

    def register(self, func: Callable, scope: str, stage: str) -> None:
        name = func.__name__
        tty.verbose(f"Registering plugin {name}::{scope}::{stage}")
        err_msg = f"register() got unexpected stage '{scope}::{stage}'"
        if scope == "main":
            if stage not in ("setup",):
                raise TypeError(err_msg)
        elif scope == "session":
            if stage not in ("setup", "teardown"):
                raise TypeError(err_msg)
        elif scope == "test":
            if stage not in ("discovery", "setup", "teardown"):
                raise TypeError(err_msg)
        else:
            raise TypeError(f"register() got unexpected scope {scope!r}")

        scope_plugins = self._plugins.setdefault(scope, {})
        stage_plugins = scope_plugins.setdefault(stage, [])
        hook: Callable = func
        hook.specname = f"{func.__name__}_impl"  # type: ignore
        stage_plugins.append(hook)

    def plugins(self, scope: str, stage: str) -> Generator[Callable, None, None]:
        for hook in self._plugins.get(scope, {}).get(stage, []):
            yield hook

    def get_plugin(self, scope: str, stage: str, name: str) -> Optional[Callable]:
        if scope in self._plugins and stage in self._plugins[scope]:
            specname = f"{name}_impl"
            for hook in self._plugins[scope][stage]:
                if hook.specname == specname:  # type: ignore
                    return hook
        return None

    def load(self, path: str) -> None:
        for file in glob.glob(os.path.join(path, "nvtest_*.py")):
            basename = os.path.splitext(os.path.basename(file))[0]
            name = f"nvtest.plugins.{basename}"
            # importing the module will load the plugins
            load_module_from_file(name, file)

    def load_from_entry_points(self):
        try:
            entry_points = im.entry_points().select().get("nvtest.plugin")
        except AttributeError:
            entry_points = im.entry_points()..get("nvtest.plugin")
        if entry_points:
            for entry_point in entry_points:
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


_manager = Singleton(Manager)


def set_args(args: Namespace) -> None:
    _manager.set_args(args)


def plugins(scope: str, stage: str) -> Generator[Callable, None, None]:
    return _manager.plugins(scope, stage)


def get(scope: str, stage: str, name: str) -> Optional[Callable]:
    return _manager.get(scope, stage, name)


def register(*, scope: str, stage: str):
    """Decorator to register a callback"""

    def decorator(func: Callable):
        functools.wraps(func)

        def wrapper(*args: Any, **kwargs: Any):
            return func(*args, **kwargs)

        _manager.register(func, scope, stage)
        return wrapper

    return decorator


def load(path: str) -> None:
    _manager.load(path)


def load_from_entry_points() -> None:
    _manager.load_from_entry_points()
