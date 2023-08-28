import functools
from typing import Any
from typing import Callable
from typing import Generator

from ..util.singleton import Singleton
from .command import command  # noqa: F401
from .command import get_command  # noqa: F401
from .command import nvtest_commands  # noqa: F401


class Manager:
    def __init__(self):
        self._plugins: dict[str, dict[str, dict[str, Callable]]] = {}

    def register(self, name: str, func: Callable, scope: str, stage: str) -> None:
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


_manager = Singleton(Manager)


def plugins(scope: str, stage: str) -> Generator[tuple[str, Callable], None, None]:
    return _manager.plugins(scope, stage)


def register(name: str, *, scope: str, stage: str):
    def inner(func: Callable):
        functools.wraps(func)

        def _func(*args: Any, **kwargs: Any):
            return func(*args, **kwargs)

        _manager.register(name, _func, scope, stage)
        return _func

    return inner
