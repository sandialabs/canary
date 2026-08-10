# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Regression test for issue 21.

This test verifies VVT asset linking behavior without invoking the Canary CLI
through a subprocess.  The VVT input declares one test that links an asset using
its original name and another test that links the same asset under a renamed
destination.  The test uses the library-level ``Workspace`` APIs to collect,
generate, and run the VVT file in-process.

The covered behavior is that linked assets are available in each job's execution
directory under the expected name, including when the VVT ``rename`` option is
used.
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


def test_issue_21(tmp_path):
    workspace = Workspace.create(tmp_path)
    f = HERE / "issue-21.vvt"

    specs = workspace.collect({str(f.parent): [f.name]})
    session = workspace.run(specs, only="all")

    assert session.returncode == 0
    assert {job.name for job in session.jobs} == {"just_link", "link_rename"}
    assert all(job.status.is_success() for job in session.jobs)
