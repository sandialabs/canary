# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for VVT asset linking and rename behavior.

Verifies that ``link`` directives make the linked asset available in each
job's execution directory, including when the VVT ``rename`` option is used.
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


def test_asset_linked_under_original_and_renamed_destination(tmp_path):
    """VVT link directive makes assets available; rename option changes the dest name."""
    workspace = Workspace.create(tmp_path)
    f = HERE / "asset_linking.vvt"

    specs = workspace.collect({str(f.parent): [f.name]})
    session = workspace.run(specs, only="all")

    assert session.returncode == 0
    assert {job.name for job in session.jobs} == {"just_link", "link_rename"}
    assert all(job.status.is_success() for job in session.jobs)
