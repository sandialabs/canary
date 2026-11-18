# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Workspace components work on every construction path (REVIEW B1)."""

import _canary.workspace.workspace as ws_module
from _canary.workspace.workspace import Workspace
from _canary.workspace.workspace import set_workspace_dir


def _exercise_components(ws: Workspace) -> None:
    assert ws.collect({}) == []  # collection
    assert ws.is_tag("no-such-tag") is False  # SpecSelector
    assert ws.load_jobs() == []  # JobReconstructor


def test_components_after_create(tmp_path):
    _exercise_components(Workspace.create(tmp_path))


def test_components_after_load(tmp_path):
    Workspace.create(tmp_path)
    _exercise_components(Workspace.load(tmp_path))


def test_components_after_load_with_workspace_override(tmp_path, monkeypatch):
    Workspace.create(tmp_path)
    # set_workspace_dir() exports CANARY_DIR; monkeypatch restores both at teardown.
    monkeypatch.delenv("CANARY_DIR", raising=False)
    monkeypatch.setattr(ws_module, "_override_workspace_dir", None)
    set_workspace_dir(tmp_path / ".canary")
    _exercise_components(Workspace.load())
