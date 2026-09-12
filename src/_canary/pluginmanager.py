# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import importlib.util
import inspect
import os
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
            self._import_plugin_from_directory(dev_dir)
        except Exception as exc:
            import warnings

            warnings.warn(f"Failed to load developer plugin from {dev_dir!r}: {exc}", stacklevel=2)

    def register_builtins(self):
        from . import collect
        from . import generate
        from . import hooks
        from . import launcher
        from . import reporters
        from . import runtest
        from . import select
        from . import subcommands
        from .resource_pool import gpu_select
        from .resource_pool import hooks as rp_hooks

        for subcommand in subcommands.plugins:
            name = subcommand.__name__.split(".")[-1].lower()
            self.register(subcommand, name=f"command.{name}")
        for p in reporters.plugins:
            name = getname(p)
            self.register(p, f"builtin.{name}")
        self.register(collect, "builtin.collect")
        self.register(hooks, "builtin.hooks")
        self.register(generate, "builtin.generate")
        self.register(gpu_select, "builtin.gpu_select")
        self.register(filter, "builtin.filter")
        self.register(launcher, "builtin.launcher")
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

    def ensure_loaded(self, name: str) -> None:
        if not self.has_plugin(name):
            self.import_plugin(name)

    def ensure_unloaded(self, name: str) -> None:
        if self.has_plugin(name):
            self.unregister(name)

    def import_plugin(self, name: str) -> None:
        """Import and register a plugin.

        Three loading modes are supported:

        1. **File path** — if *name* ends with ``.py`` and names an existing
           file, the file is loaded as a module whose registration name is the
           file stem (e.g. ``myhooks.py`` → registered as ``myhooks``).

        2. **Directory path** — if *name* names an existing directory the
           directory is treated as a package; its ``__init__.py`` is loaded and
           the registration name is the directory's base name.

        3. **Module name** — otherwise *name* is treated as a dotted Python
           module name and imported via the normal import machinery (the
           existing behaviour).

        In all cases the ``no:`` prefix recognised by :meth:`consider_plugin`
        uses the registration name, not the original path.
        """
        assert isinstance(name, str), f"module name as text required, got {name!r}"

        # ------------------------------------------------------------------ #
        # File-path loading: -p /path/to/myhooks.py                          #
        # ------------------------------------------------------------------ #
        if name.endswith(".py") and os.path.isfile(name):
            self._import_plugin_from_file(name)
            return

        # ------------------------------------------------------------------ #
        # Directory / package loading: -p /path/to/mypkg                     #
        # ------------------------------------------------------------------ #
        if os.path.isdir(name):
            self._import_plugin_from_directory(name)
            return

        # ------------------------------------------------------------------ #
        # Ordinary dotted module name (original behaviour)                   #
        # ------------------------------------------------------------------ #
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

    # ---------------------------------------------------------------------- #
    # Private helpers                                                         #
    # ---------------------------------------------------------------------- #

    def _import_plugin_from_file(self, path: str) -> None:
        """Load *path* (a ``.py`` file) as a plugin module.

        The module is registered under the file stem so that ``no:<stem>``
        can later unload it.  The module is also inserted into ``sys.modules``
        under the same stem name so that relative imports inside the file
        (if any) can resolve.
        """
        import pathlib

        stem = pathlib.Path(path).stem
        abs_path = os.path.abspath(path)

        if self.is_blocked(stem) or self.get_plugin(stem) is not None:
            return

        spec = importlib.util.spec_from_file_location(stem, abs_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for plugin file {path!r}")

        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault(stem, mod)
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except Exception as e:
            sys.modules.pop(stem, None)
            msg = f"Error loading plugin file {path!r}: {e}"
            raise ImportError(msg) from e

        if mod in self._name2plugin.values():
            other = next(k for k, v in self._name2plugin.items() if v == mod)
            msg = f"Plugin {path!r} already registered under the name {other!r}"
            raise PluginAlreadyImportedError(msg)

        self.register(mod, stem)

    def _import_plugin_from_directory(self, path: str) -> None:
        """Load *path* (a directory) as a plugin package.

        The directory's ``__init__.py`` is executed and the package is
        registered under the directory's base name.  The package is also
        inserted into ``sys.modules`` so intra-package imports work.
        """
        import pathlib

        pkg_name = pathlib.Path(path).name
        abs_path = os.path.abspath(path)
        init = os.path.join(abs_path, "__init__.py")

        if not os.path.isfile(init):
            raise ImportError(
                f"Plugin directory {path!r} does not contain an __init__.py; "
                "it cannot be loaded as a package."
            )

        if self.is_blocked(pkg_name) or self.get_plugin(pkg_name) is not None:
            return

        spec = importlib.util.spec_from_file_location(
            pkg_name, init, submodule_search_locations=[abs_path]
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for plugin directory {path!r}")

        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault(pkg_name, mod)
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except Exception as e:
            sys.modules.pop(pkg_name, None)
            msg = f"Error loading plugin directory {path!r}: {e}"
            raise ImportError(msg) from e

        if mod in self._name2plugin.values():
            other = next(k for k, v in self._name2plugin.items() if v == mod)
            msg = f"Plugin {path!r} already registered under the name {other!r}"
            raise PluginAlreadyImportedError(msg)

        self.register(mod, pkg_name)


def getname(obj: Any) -> str:
    if inspect.ismodule(obj):
        return obj.__name__.split(".")[-1].lower()
    elif type(obj) is type:
        return obj.__name__.lower()
    else:
        return type(obj).__name__.lower()


class PluginAlreadyImportedError(Exception): ...
