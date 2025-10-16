# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys
import warnings

import pluggy

from . import builtin
from . import hookspec
from . import subcommands

warnings.simplefilter("once", DeprecationWarning)


class CanaryPluginManager(pluggy.PluginManager):
    @classmethod
    def factory(cls) -> "CanaryPluginManager":
        self = cls(hookspec.project_name)
        self.add_hookspecs(hookspec)
        for subcommand in subcommands.plugins:
            name = subcommand.__name__.split(".")[-1].lower()
            self.register(subcommand, name=name)
        for p in builtin.plugins:
            name = p.__name__.split(".")[-1].lower()
            self.register(p, name=name)
        for p in builtin.plugin_instances:
            self.register(p, name=f"builtin.{type(p).__name__.lower()}")
        self.load_setuptools_entrypoints(hookspec.project_name)
        return self

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


class PluginAlreadyImportedError(Exception): ...
