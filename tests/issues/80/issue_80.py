# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Regression test for issue 80.

This test verifies parameter-expression parsing for values such as ``2D``.
Historically, expressions like ``dim=2D`` could be tokenized incorrectly because
``2D`` combines a numeric prefix with a string suffix.  The test avoids invoking
``canary run -p`` through a subprocess and instead uses ``Workspace`` selection
APIs directly.

The covered behavior is that selecting with ``parameter_expr="dim=2D"`` returns
only the generated VVT specs whose ``dim`` parameter is exactly ``2D``.
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
            _canary.config.pluginmanager.ensure_loaded("canary_vvtest")
        except Exception:
            pass
        yield


def test_issue_80(tmp_path):
    workspace = Workspace.create(tmp_path)
    f = HERE / "issue-80.vvt"

    specs = workspace.collect({str(f.parent): [f.name]})
    selected = workspace.select_from_specs(specs, parameter_expr="dim=2D")
    selected = [spec for spec in selected if not spec.mask]

    assert len(selected) == 4
    assert {spec.parameters["dim"] for spec in selected} == {"2D"}
    assert {spec.parameters["input"] for spec in selected} == {
        "flyer_2d_z",
        "flyer_2d_y",
        "flyer_2d_y_eul",
        "flyer_2d_z_eul",
    }
