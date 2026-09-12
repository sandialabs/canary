# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for CanaryPluginManager file-path and directory-path loading modes.

Covers:
  - import_plugin("path/to/myhook.py")  — single-file module
  - import_plugin("path/to/mypkg/")     — package directory
  - consider_plugin("no:<stem>") unloads a file/dir plugin by stem name
  - duplicate-registration is silently skipped
  - missing __init__.py raises ImportError
  - syntax errors inside the file/directory raise ImportError
"""

import sys
from pathlib import Path

import pytest

from _canary.pluginmanager import CanaryPluginManager

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def pm():
    """A bare PluginManager without builtins (faster, no side-effects)."""
    from _canary import hookspec

    mgr = CanaryPluginManager(hookspec.project_name)
    mgr.add_hookspecs(hookspec)
    return mgr


def _write_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _write_package(base: Path, pkg_name: str, init_content: str) -> Path:
    pkg = base / pkg_name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(init_content)
    return pkg


# --------------------------------------------------------------------------- #
# Single-file (.py) loading                                                    #
# --------------------------------------------------------------------------- #


def test_import_plugin_from_file_registers_by_stem(tmp_path, pm):
    """A .py file plugin is registered under its stem name."""
    hook_file = _write_file(tmp_path / "myhook.py", "SENTINEL = 42\n")
    pm.import_plugin(str(hook_file))
    assert pm.get_plugin("myhook") is not None


def test_import_plugin_from_file_stem_in_sys_modules(tmp_path, pm):
    """The loaded module is present in sys.modules under its stem."""
    hook_file = _write_file(tmp_path / "sysmod_hook.py", "VALUE = 99\n")
    pm.import_plugin(str(hook_file))
    assert "sysmod_hook" in sys.modules
    assert sys.modules["sysmod_hook"].VALUE == 99  # type: ignore[attr-defined]


def test_import_plugin_from_file_module_attributes_accessible(tmp_path, pm):
    """Attributes defined in the loaded file are accessible via get_plugin."""
    hook_file = _write_file(tmp_path / "attr_hook.py", "MAGIC = 'hello'\n")
    pm.import_plugin(str(hook_file))
    mod = pm.get_plugin("attr_hook")
    assert mod is not None
    assert mod.MAGIC == "hello"  # type: ignore[attr-defined]


def test_import_plugin_from_file_idempotent(tmp_path, pm):
    """Calling import_plugin a second time with the same file is a no-op."""
    hook_file = _write_file(tmp_path / "idem_hook.py", "X = 1\n")
    pm.import_plugin(str(hook_file))
    pm.import_plugin(str(hook_file))  # must not raise
    # still exactly one registration
    plugins_named = [p for p in pm.get_plugins() if pm.get_name(p) == "idem_hook"]
    assert len(plugins_named) == 1


def test_import_plugin_from_file_blocked_is_skipped(tmp_path, pm):
    """A file plugin whose stem is blocked is not loaded."""
    hook_file = _write_file(tmp_path / "blocked_hook.py", "X = 1\n")
    pm.set_blocked("blocked_hook")
    pm.import_plugin(str(hook_file))
    assert pm.get_plugin("blocked_hook") is None


def test_import_plugin_from_file_syntax_error_raises(tmp_path, pm):
    """A syntax error in the plugin file raises ImportError."""
    bad_file = _write_file(tmp_path / "bad_hook.py", "def (: pass\n")
    with pytest.raises(ImportError, match="bad_hook"):
        pm.import_plugin(str(bad_file))


def test_import_plugin_from_file_relative_path(tmp_path, pm, monkeypatch):
    """A relative .py path is resolved to an absolute location before loading."""
    hook_file = _write_file(tmp_path / "rel_hook.py", "REL = True\n")
    monkeypatch.chdir(tmp_path)
    pm.import_plugin("rel_hook.py")
    assert pm.get_plugin("rel_hook") is not None


# --------------------------------------------------------------------------- #
# Directory / package loading                                                  #
# --------------------------------------------------------------------------- #


def test_import_plugin_from_directory_registers_by_dirname(tmp_path, pm):
    """A directory plugin is registered under the directory base name."""
    pkg = _write_package(tmp_path, "mypkg", "SENTINEL = 7\n")
    pm.import_plugin(str(pkg))
    assert pm.get_plugin("mypkg") is not None


def test_import_plugin_from_directory_in_sys_modules(tmp_path, pm):
    """The loaded package is present in sys.modules under its base name."""
    pkg = _write_package(tmp_path, "sys_pkg", "VALUE = 55\n")
    pm.import_plugin(str(pkg))
    assert "sys_pkg" in sys.modules
    assert sys.modules["sys_pkg"].VALUE == 55  # type: ignore[attr-defined]


def test_import_plugin_from_directory_attributes_accessible(tmp_path, pm):
    """Attributes defined in __init__.py are accessible via get_plugin."""
    pkg = _write_package(tmp_path, "attr_pkg", "KEY = 'world'\n")
    pm.import_plugin(str(pkg))
    mod = pm.get_plugin("attr_pkg")
    assert mod is not None
    assert mod.KEY == "world"  # type: ignore[attr-defined]


def test_import_plugin_from_directory_idempotent(tmp_path, pm):
    """Calling import_plugin a second time with the same directory is a no-op."""
    pkg = _write_package(tmp_path, "idem_pkg", "X = 1\n")
    pm.import_plugin(str(pkg))
    pm.import_plugin(str(pkg))  # must not raise
    plugins_named = [p for p in pm.get_plugins() if pm.get_name(p) == "idem_pkg"]
    assert len(plugins_named) == 1


def test_import_plugin_from_directory_blocked_is_skipped(tmp_path, pm):
    """A directory plugin whose name is blocked is not loaded."""
    pkg = _write_package(tmp_path, "blocked_pkg", "X = 1\n")
    pm.set_blocked("blocked_pkg")
    pm.import_plugin(str(pkg))
    assert pm.get_plugin("blocked_pkg") is None


def test_import_plugin_from_directory_missing_init_raises(tmp_path, pm):
    """A directory without __init__.py raises ImportError."""
    bare_dir = tmp_path / "bare_dir"
    bare_dir.mkdir()
    with pytest.raises(ImportError, match="__init__.py"):
        pm.import_plugin(str(bare_dir))


def test_import_plugin_from_directory_init_syntax_error_raises(tmp_path, pm):
    """A syntax error in __init__.py raises ImportError."""
    pkg = _write_package(tmp_path, "bad_pkg", "def (: pass\n")
    with pytest.raises(ImportError, match="bad_pkg"):
        pm.import_plugin(str(pkg))


def test_import_plugin_from_directory_relative_path(tmp_path, pm, monkeypatch):
    """A relative directory path is resolved to an absolute location."""
    pkg = _write_package(tmp_path, "rel_pkg", "REL = True\n")
    monkeypatch.chdir(tmp_path)
    pm.import_plugin("rel_pkg")
    assert pm.get_plugin("rel_pkg") is not None


# --------------------------------------------------------------------------- #
# consider_plugin with no: prefix                                              #
# --------------------------------------------------------------------------- #


def test_consider_plugin_no_prefix_unloads_file_plugin(tmp_path, pm):
    """no:<stem> unloads a previously loaded file plugin."""
    hook_file = _write_file(tmp_path / "unload_hook.py", "X = 1\n")
    pm.import_plugin(str(hook_file))
    assert pm.get_plugin("unload_hook") is not None
    pm.consider_plugin("no:unload_hook")
    assert pm.get_plugin("unload_hook") is None
    assert pm.is_blocked("unload_hook")


def test_consider_plugin_no_prefix_unloads_directory_plugin(tmp_path, pm):
    """no:<pkgname> unloads a previously loaded directory plugin."""
    pkg = _write_package(tmp_path, "unload_pkg", "X = 1\n")
    pm.import_plugin(str(pkg))
    assert pm.get_plugin("unload_pkg") is not None
    pm.consider_plugin("no:unload_pkg")
    assert pm.get_plugin("unload_pkg") is None
    assert pm.is_blocked("unload_pkg")


def test_consider_plugin_file_path_loads_plugin(tmp_path, pm):
    """consider_plugin with a .py path delegates to import_plugin correctly."""
    hook_file = _write_file(tmp_path / "consider_hook.py", "X = 1\n")
    pm.consider_plugin(str(hook_file))
    assert pm.get_plugin("consider_hook") is not None


def test_consider_plugin_directory_path_loads_plugin(tmp_path, pm):
    """consider_plugin with a directory path delegates to import_plugin correctly."""
    pkg = _write_package(tmp_path, "consider_pkg", "X = 1\n")
    pm.consider_plugin(str(pkg))
    assert pm.get_plugin("consider_pkg") is not None
