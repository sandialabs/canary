import bisect
import functools
import inspect
from functools import wraps
from typing import Any
from typing import Callable
from typing import Generator
from typing import Optional
from typing import Type

from .util import tty
from .util.singleton import Singleton


class Manager:
    def __init__(self):
        self._plugins: dict[str, dict[str, dict[str, Callable]]] = {}
        self._cli_commands: list[Type] = []

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

    def _add_command(self, cmdclass: Type, family: str):
        order = {"info": 0, "batching": 1, "testing": 2}.get(family, 10)
        cmdclass._order_ = order
        bisect.insort(self._cli_commands, cmdclass, key=lambda x: (x._order_, x.name))

    def cli_commands(self) -> list[Type]:
        return self._cli_commands

    def get_command(self, cmdname: str) -> Optional[Type]:
        for cmdclass in self._cli_commands:
            if cmdname == cmdclass.name:
                return cmdclass
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


def commands():
    return _manager.cli_commands()


def get_command(cmdname):
    return _manager.get_command(cmdname)


def command(*args, **kwargs):
    """Decorator for registering a CLI command"""

    def _defines_method(cls, method_name):
        method = getattr(cls, method_name, None)
        return callable(method)

    def _command(cmdclass: object):
        if not inspect.isclass(cmdclass):
            raise TypeError("nvtest.plugins.command must wrap classes")

        for method in ("add_options", "setup", "run", "teardown"):
            if not _defines_method(cmdclass, method):
                raise AttributeError(
                    f"{cmdclass.__name__} must define a {method} method"
                )

        for attr in ("description",):
            if not hasattr(cmdclass, attr):
                raise AttributeError(
                    f"{cmdclass.__name__} must define a {attr} attribute"
                )

        if not hasattr(cmdclass, "name"):
            cmdclass.name = cmdclass.__name__.lower()
        _manager._add_command(cmdclass, family)

        @wraps(cmdclass, updated=())
        class _wrapped(cmdclass):  # type: ignore
            ...

        return _wrapped

    if len(args) > 1:
        n = len(args)
        raise TypeError(f"command() takes 1 positional argument but {n} were given")
    elif args and kwargs:
        family = kwargs.pop("family", None)
        if kwargs:
            kwd = next(iter(kwargs))
            raise TypeError(f"command() got an unexpected keyword argument {kwd!r}")
        return _command(args[0])
    elif kwargs:
        family = kwargs.pop("family", None)
        if kwargs:
            kwd = next(iter(kwargs))
            raise TypeError(f"command() got an unexpected keyword argument {kwd!r}")
        return _command
    elif args:
        family = None
        return _command(args[0])
    else:
        family = None
        return _command


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
