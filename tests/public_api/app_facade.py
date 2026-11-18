# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Workspace create/load round trip, and ``_canary.app`` staying off the eager import path.

Interfaces open workspaces with :meth:`Workspace.load`/:meth:`Workspace.create`
directly; ``canary.app`` must stay off the eager ``import canary`` path so test
subprocesses keep paying nothing for it until first use.
"""

import sys

import pytest

import _canary.workspace.workspace as _workspace_module
from _canary.workspace.workspace import NotAWorkspaceError
from _canary.workspace.workspace import Workspace


@pytest.fixture(autouse=True)
def reset_workspace_override():
    _workspace_module._override_workspace_dir = None
    yield
    _workspace_module._override_workspace_dir = None


def test_create_then_open_round_trips_to_same_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "proj"
    root.mkdir()

    created = Workspace.create(root)
    opened = Workspace.load(root)

    assert opened.root == created.root


def test_open_missing_workspace_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(NotAWorkspaceError):
        Workspace.load(tmp_path)


def test_app_is_not_on_the_eager_import_path():
    """``canary.app`` is lazy: importing it must not be forced by ``import canary``.

    This protects the startup-latency contract that ``canary/__init__.py``
    deliberately maintains for test subprocesses.
    """
    import importlib

    saved = {name: sys.modules[name] for name in ("canary", "_canary.app") if name in sys.modules}
    try:
        for name in ("canary", "_canary.app"):
            sys.modules.pop(name, None)

        importlib.import_module("canary")
        assert "_canary.app" not in sys.modules

        import canary

        assert canary.app is importlib.import_module("_canary.app")
    finally:
        # Restore the original module objects so later tests that captured
        # ``_canary.app`` at import time keep identity with the live module.
        sys.modules.update(saved)
