# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for parameter-expression parsing with alphanumeric values.

Verifies that expressions like ``dim=2D`` are tokenized correctly even though
``2D`` combines a numeric prefix with a string suffix.
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
        _canary.config.pluginmanager.ensure_loaded("canary_vvtest")
        yield


def test_alphanumeric_parameter_value_selected_exactly(tmp_path):
    """parameter_expr='dim=2D' selects only specs with that exact parameter value."""
    workspace = Workspace.create(tmp_path)
    f = HERE / "param_expr_alphanumeric.vvt"

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
