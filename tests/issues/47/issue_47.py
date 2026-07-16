# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Regression test for issue 47.

This test verifies VVT ``include`` directives combined with parameterization
without invoking Canary through the CLI.  The VVT file defines multiple test
names, includes additional directives from a neighboring text file, and applies
separate parameterizations to different test names.

The regression is covered entirely at generation time: the test uses
``Workspace.collect`` and asserts that the generated runnable specs have the
expected parameterized names.
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


def test_issue_47(tmp_path):
    workspace = Workspace.create(tmp_path)
    f = HERE / "issue-47.vvt"

    specs = workspace.collect({str(f.parent): [f.name]})
    specs = [spec for spec in specs if not spec.mask]

    assert {spec.name for spec in specs} == {
        "test2.arg3=apple",
        "test2.arg3=strawberry",
        "test4.arg1=pear.arg2=kiwi",
        "test4.arg1=pear.arg2=pineapple",
        "test4.arg1=plum.arg2=kiwi",
        "test4.arg1=plum.arg2=pineapple",
    }
