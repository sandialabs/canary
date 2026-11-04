# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import inspect
import os
import pathlib
import sys
import warnings
from typing import Any

import pluggy

from . import hookspec
from .specs import normalize_plugin_spec

warnings.simplefilter("once", DeprecationWarning)


class CanaryPluginManager(pluggy.PluginManager):
    @classmethod
    def factory(cls) -> "CanaryPluginManager":
        self = cls(hookspec.project_name)
        self.add_hookspecs(hookspec)
        self.register_builtins()
        self.load_setuptools_entrypoints(hookspec.project_name)
        self._load_dev_plugin()
        return self

    def _load_dev_plugin(self) -> None:
        """Load ``dev/`` from the repository root when running an editable install.

        Detection logic:
          1. Resolve the canary package location via ``importlib.resources``.
          2. Walk two levels up (``src/canary`` → repo root).
          3. If a ``.git/`` directory is present there it is an editable
             checkout.
          4. If a ``dev/`` directory also exists there, load it as a plugin
             package using :meth:`_import_plugin_from_directory`.

        This is intentionally silent: if the conditions are not met (installed
        release, no ``.git``, no ``dev/``) the method does nothing.
        """
        import importlib.resources as ir

        try:
            root_traversable = ir.files("canary").joinpath("../..")
            root = os.path.normpath(str(root_traversable))
        except Exception:
            return

        if not os.path.isdir(os.path.join(root, ".git")):
            return

        dev_dir = os.path.join(root, "dev")
        if not os.path.isdir(dev_dir):
            return

        try:
            self.import_plugin_spec(
                {"name": os.path.basename(dev_dir), "path": os.path.dirname(dev_dir)}
            )
        except Exception as exc:
            import warnings

            warnings.warn(f"Failed to load developer plugin from {dev_dir!r}: {exc}", stacklevel=2)

    def register_builtins(self):
        from .. import cli
        from .. import reporters
        from .. import select
        from ..execution import launcher
        from ..execution import runtest
        from ..generation import collect
        from ..generation import generate
        from ..resource_pool import gpu_select
        from ..resource_pool import hooks as rp_hooks
        from . import canaryconf_impl
        from . import hooks
        from . import user_execspace

        for subcommand in cli.plugins:
            name = subcommand.__name__.split(".")[-1].lower()
            self.register(subcommand, name=f"command.{name}")
        for p in reporters.plugins:
            name = getname(p)
            self.register(p, f"builtin.{name}")
        self.register(collect, "builtin.collect")
        self.register(hooks, "builtin.hooks")
        self.register(generate, "builtin.generate")
        self.register(gpu_select, "builtin.gpu_select")
        self.register(launcher, "builtin.launcher")
        self.register(runtest, "builtin.runtest")
        self.register(rp_hooks, "builtin.resource_pool")
        self.register(canaryconf_impl, "builtin.canaryconf_impl")
        self.register(select, "builtin.select")
        self.register(user_execspace, "builtin.user_execspace")

    def consider_plugin(self, name: str) -> None:
        assert isinstance(name, str), f"module name as text required, got {name!r}"
        if name.startswith("no:"):
            normalized = derive_plugin_name(name[3:])
            self.unregister(name=normalized)
            self.set_blocked(normalized)
        else:
            self.import_plugin(name)

    def consider_plugin_spec(self, spec: dict[str, str]) -> None:
        self.import_plugin_spec(spec)

    def ensure_loaded(self, name: str) -> None:
        if not self.has_plugin(name):
            self.import_plugin(name)

    def ensure_unloaded(self, name: str) -> None:
        if self.has_plugin(name):
            self.unregister(name)

    def import_plugin(self, name: str) -> None:
        spec = normalize_plugin_spec(name)
        self.import_plugin_spec(spec)

    def import_plugin_spec(self, spec: dict[str, str]) -> None:
        """Import and register a plugin.

        The normalized spec contains the module/package name and optionally a
        directory to prepend to ``sys.path`` before import.
        """
        name = spec["name"]
        if self.is_blocked(name):
            return

        if self.get_plugin(name) is not None:
            existing = self.get_plugin(name)
            existing_file = getattr(existing, "__file__", None) if existing is not None else None
            if existing_file is not None and spec.get("path") is not None:
                expected = os.path.abspath(os.path.join(spec["path"], f"{name}.py"))
                expected_pkg = os.path.abspath(os.path.join(spec["path"], name, "__init__.py"))
                actual = os.path.abspath(existing_file)
                if actual in (expected, expected_pkg):
                    return
            if spec.get("path") is None:
                return
            raise PluginAlreadyImportedError(
                f"Plugin {name!r} already registered from a different import path"
            )

        path = spec.get("path")
        if path and path not in sys.path:
            sys.path.insert(0, path)

        try:
            __import__(name)
        except Exception as e:
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


def derive_plugin_name(name: str) -> str:
    path = pathlib.Path(name)
    if name.endswith(".py"):
        return path.stem
    if os.path.isdir(name):
        return path.name
    return name
