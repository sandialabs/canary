# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Regression test for issue 84.

This test verifies that keyword-specific timeout configuration is applied during
spec generation.  The original test drove ``canary init``, ``canary config
set``, ``canary selection create``, and ``canary run`` through subprocesses.
This replacement sets the relevant configuration value directly and uses
``Workspace.collect`` to generate specs in-process.

The covered behavior is that a PYT test marked with keyword ``baz`` receives the
configured ``run:timeout:baz`` value of four minutes.
"""

from pathlib import Path

import pytest

import _canary.config
from _canary.workspace import Workspace

HERE = Path(__file__).parent


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.delenv("CANARYCFG64", raising=False)
    monkeypatch.delenv("CANARYCFGFILE", raising=False)
    monkeypatch.setenv("CANARY_DISABLE_KB", "1")
    monkeypatch.chdir(tmp_path)

    with _canary.config.override():
        try:
            _canary.config.pluginmanager.ensure_loaded("canary_pyt")
        except Exception:
            pass
        yield


def test_issue_84(tmp_path):
    _canary.config.set("run:timeout:baz", "4m")

    workspace = Workspace.create(tmp_path)
    f = HERE / "issue-84.pyt"

    specs = workspace.collect({str(f.parent): [f.name]})
    specs = [spec for spec in specs if not spec.mask]

    assert len(specs) == 1
    assert specs[0].family == "issue-84"
    assert specs[0].keywords == ["baz"]
    assert specs[0].timeout == 240.0
