# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import inspect
import sys
import warnings
from typing import Any

import pluggy

from . import hookspec

warnings.simplefilter("once", DeprecationWarning)


class CanaryPluginManager(pluggy.PluginManager):
    @classmethod
    def factory(cls) -> "CanaryPluginManager":
        self = cls(hookspec.project_name)
        self.add_hookspecs(hookspec)
        self.register_builtins()
        self.load_setuptools_entrypoints(hookspec.project_name)
        return self

    def register_builtins(self):
        from . import build
        from . import collect
        from . import executor
        from . import runtest
        from . import select
        from .plugins import builtin
        from .plugins import subcommands
        from .resource_pool import hooks as rp_hooks

        for subcommand in subcommands.plugins:
            name = subcommand.__name__.split(".")[-1].lower()
            self.register(subcommand, name=f"command.{name}")
        for p in builtin.plugins:
            name = getname(p)
            self.register(p, f"builtin.{name}")
        self.register(collect, "builtin.collect")
        self.register(executor.TestCaseExecutor(), "builtin.executor")
        self.register(build, "builtin.build")
        self.register(runtest, "builtin.runtest")
        self.register(rp_hooks, "builtin.resource_pool")
        self.register(select, "builtin.select")

    def consider_plugin(self, name: str) -> None:
        assert isinstance(name, str), f"module name as text required, got {name!r}"
        if name.startswith("no:"):
            self.unregister(name=name[3:])
            self.set_blocked(name[3:])
        else:
            self.import_plugin(name)

    def import_plugin(self, name: str) -> None:
        """Import a plugin with ``name``."""
        assert isinstance(name, str), f"module name as text required, got {name!r}"

        if self.is_blocked(name) or self.get_plugin(name) is not None:
            return

        try:
            __import__(name)
        except ImportError as e:
            msg = f"Error importing plugin {name!r}: {e.args[0]}"
            raise ImportError(msg).with_traceback(e.__traceback__) from e
        else:
            mod = sys.modules[name]
            if mod in self._name2plugin.values():
                other = next(k for k, v in self._name2plugin.items() if v == mod)
                msg = f"Plugin {name} already registered under the name {other}"
                raise PluginAlreadyImportedError(msg)
            self.register(mod, name)


def getname(obj: Any) -> str:
    if inspect.ismodule(obj):
        return obj.__name__.split(".")[-1].lower()
    elif type(obj) is type:
        return obj.__name__.lower()
    else:
        return type(obj).__name__.lower()


class PluginAlreadyImportedError(Exception): ...
