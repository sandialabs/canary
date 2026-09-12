# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for keyword-specific timeout configuration applied at spec generation.

Verifies that a PYT test marked with a keyword receives the configured
``run:timeout:<keyword>`` value when specs are collected.
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
        _canary.config.pluginmanager.ensure_loaded("canary_pyt")
        yield


def test_keyword_timeout_config_applied_during_collection(tmp_path):
    """run:timeout:<keyword> config is reflected in the generated spec's timeout."""
    _canary.config.set("run:timeout:baz", "4m")

    workspace = Workspace.create(tmp_path)
    f = HERE / "keyword_timeout.pyt"

    specs = workspace.collect({str(f.parent): [f.name]})
    specs = [spec for spec in specs if not spec.mask]

    assert len(specs) == 1
    assert specs[0].family == "keyword_timeout"
    assert specs[0].keywords == ["baz"]
    assert specs[0].timeout == 240.0
