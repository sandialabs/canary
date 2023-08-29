import functools
from typing import Any
from typing import Callable
from typing import Generator
from typing import Optional

from .util import tty
from .util.singleton import Singleton


class Manager:
    def __init__(self):
        self._plugins: dict[str, dict[str, dict[str, Callable]]] = {}

    def register(self, name: str, func: Callable, scope: str, stage: str) -> None:
        tty.verbose(f"Registering plugin {name}::{scope}::{stage}")
        if scope == "session":
            if stage not in ("bootstrap", "setup", "teardown"):
                raise TypeError(f"register() got unexpected stage {stage!r}")
        elif scope == "test":
            if stage not in ("setup", "teardown"):
                raise TypeError(f"register() got unexpected stage {stage!r}")
        else:
            raise TypeError(f"register() got unexpected scope {scope!r}")

        scope_plugins = self._plugins.setdefault(scope, {})
        stage_plugins = scope_plugins.setdefault(stage, {})
        stage_plugins[name] = func

    def plugins(
        self, scope: str, stage: str
    ) -> Generator[tuple[str, Callable], None, None]:
        pl = {}
        if scope in self._plugins and stage in self._plugins[scope]:
            pl = self._plugins[scope][stage]
        for (name, func) in pl.items():
            yield name, func

    def get_plugin(self, scope: str, stage: str, name: str) -> Optional[Any]:
        if scope in self._plugins and stage in self._plugins[scope]:
            return self._plugins[scope][stage].get(name)
        return None

    def load(self, path: list[str], namespace: str) -> None:
        import importlib
        import pkgutil

        for finder, name, ispkg in pkgutil.iter_modules(path, namespace + "."):
            if name.startswith(f"{namespace}.nvtest_"):
                # importing the module will load the plugins
                importlib.import_module(name)


_manager = Singleton(Manager)


def plugins(scope: str, stage: str) -> Generator[tuple[str, Callable], None, None]:
    return _manager.plugins(scope, stage)


def get(scope: str, stage: str, name: str) -> Optional[Any]:
    return _manager.get(scope, stage, name)


def register(name: str, *, scope: str, stage: str):
    """Decorator for register a callback"""

    def inner(func: Callable):
        functools.wraps(func)

        def _func(*args: Any, **kwargs: Any):
            return func(*args, **kwargs)

        _manager.register(name, _func, scope, stage)
        return _func

    return inner


def load(path: list[str], namespace: str) -> None:
    _manager.load(path, namespace)
