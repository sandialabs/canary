# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import sys
import warnings
from typing import TYPE_CHECKING
from typing import Any

import pluggy

from . import builtin
from . import hookspec
from . import subcommands
from .types import CanarySubcommand

if TYPE_CHECKING:
    from ..generator import AbstractTestGenerator


warnings.simplefilter("once", DeprecationWarning)


class CanaryPluginManager(pluggy.PluginManager):
    def __init__(self, project_name: str):
        super().__init__(project_name)
        self.considered: set[str] = set()

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
        self.load_setuptools_entrypoints(hookspec.project_name)
        self.load_from_env()
        return self

    def update(self, arg: dict[str, Any]) -> None:
        if plugins := arg.get("plugins"):
            for plugin in plugins:
                self.consider_plugin(plugin)

    def get_subcommands(self) -> list[CanarySubcommand]:
        hook = self.hook.canary_subcommand
        return hook()

    def testcase_generator(
        self, root: str, path: str | None = None
    ) -> "AbstractTestGenerator | None":
        if generator := self.hook.canary_generator(root=root, path=path):
            return generator
        for gen_type in self.hook.canary_testcase_generator():
            if gen_type.matches(root if path is None else os.path.join(root, path)):
                warnings.warn(
                    "canary_testcase_generator has been deprecated, use canary_generator instead",
                    category=DeprecationWarning,
                )
                return gen_type(root, path=path)
        return None

    def load_from_env(self) -> None:
        if plugins := os.getenv("CANARY_PLUGINS"):
            for plugin in plugins.split(","):
                self.consider_plugin(plugin)

    def consider_plugin(self, name: str) -> None:
        assert isinstance(name, str), f"module name as text required, got {name!r}"
        if name.startswith("no:"):
            self.set_blocked(name[3:])
        else:
            self.import_plugin(name)
        self.considered.add(name)

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
            self.register(mod, name)
