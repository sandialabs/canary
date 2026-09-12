# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for VVT ``include`` directives combined with parameterization.

Verifies that a VVT file that defines multiple test names, includes additional
directives from a neighboring text file, and applies separate parameterizations
to different test names generates the expected set of runnable specs.
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


def test_include_directive_with_per_testname_parameterize(tmp_path):
    """Parameterizations from an included file combine with inline ones correctly."""
    workspace = Workspace.create(tmp_path)
    f = HERE / "include_parameterize.vvt"

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
