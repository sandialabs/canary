import functools
from typing import Any
from typing import Callable
from typing import Generator
from typing import Optional

from .util import tty
from .util.singleton import Singleton


class Manager:
    def __init__(self):
        self._plugins: dict[str, dict[str, list[Callable]]] = {}

    def register(self, func: Callable, scope: str, stage: str) -> None:
        name = func.__name__
        tty.verbose(f"Registering plugin {name}::{scope}::{stage}")
        err_msg = f"register() got unexpected stage '{scope}::{stage}'"
        if scope == "cli":
            if stage not in ("setup",):
                raise TypeError(err_msg)
        elif scope == "session":
            if stage not in ("setup", "finish"):
                raise TypeError(err_msg)
        elif scope == "test":
            if stage not in ("discovery", "setup", "finish"):
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

    def load(self, path: list[str], namespace: str) -> None:
        import importlib
        import pkgutil

        for finder, name, ispkg in pkgutil.iter_modules(path, namespace + "."):
            if name.startswith(f"{namespace}.nvtest_"):
                # importing the module will load the plugins
                importlib.import_module(name)


_manager = Singleton(Manager)


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


def load(path: list[str], namespace: str) -> None:
    _manager.load(path, namespace)
