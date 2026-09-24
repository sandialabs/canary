# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""The clean subcommands must acquire their workspace through the app facade.

Routing workspace access through ``_canary.app`` (rather than calling
``Workspace`` directly) is the layering invariant established when the CLI began
delegating to the application facade.  A future edit could silently reintroduce
a direct ``Workspace.load()``/``Workspace.create()`` call; this test fails when
that happens so the seam is not lost.

Commands still entangled with orchestration or raw SQL (``run``, ``query``) are
intentionally excluded until their logic is moved behind the facade.
"""

import importlib
import inspect

import pytest

# Subcommand module -> the facade functions it is expected to use.
FACADE_ROUTED_COMMANDS = {
    "collect": {"collect"},
    "gc": {"open_workspace"},
    "init": {"create_workspace"},
    "view": {"open_workspace"},
    "location": {"open_workspace"},
    "log": {"open_workspace"},
    "select": {"open_workspace"},
    "selection": {"open_workspace"},
    "describe": {"open_workspace"},
    "edit": {"open_workspace"},
    "info": {"open_workspace"},
    "status": {"open_workspace"},
}


@pytest.mark.parametrize("modname, expected", sorted(FACADE_ROUTED_COMMANDS.items()))
def test_clean_subcommand_uses_app_facade(modname, expected):
    import _canary.app as app

    module = importlib.import_module(f"_canary.subcommands.{modname}")

    imported = getattr(module, "app", None)
    assert imported is not None and getattr(imported, "__name__", None) == "_canary.app", (
        f"{modname} should import the app facade"
    )
    for fn in expected:
        assert hasattr(app, fn)


@pytest.mark.parametrize("modname", sorted(FACADE_ROUTED_COMMANDS))
def test_clean_subcommand_does_not_call_workspace_directly(modname):
    """Guard against reintroducing a direct ``Workspace.load``/``.create`` call."""
    module = importlib.import_module(f"_canary.subcommands.{modname}")
    source = inspect.getsource(module)

    assert "Workspace.load(" not in source, f"{modname} should route load through app"
    assert "Workspace.create(" not in source, f"{modname} should route create through app"


# Commands whose domain data access has been fully hoisted behind the facade:
# they must not reach into the repository (``workspace.db``) directly.
NO_DIRECT_DB_COMMANDS = {"collect", "gc", "init", "view", "select", "selection", "info", "status"}


@pytest.mark.parametrize("modname", sorted(NO_DIRECT_DB_COMMANDS))
def test_migrated_subcommand_does_not_touch_the_database_directly(modname):
    """Guard against reintroducing raw ``workspace.db`` access in a migrated command."""
    module = importlib.import_module(f"_canary.subcommands.{modname}")
    source = inspect.getsource(module)

    assert ".db." not in source, (
        f"{modname} should read/write through the app facade, not workspace.db"
    )
