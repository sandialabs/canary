# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Regression tests for issue 89.

These tests verify dependency-pattern substitution for floating-point parameter
values in both VVT and PYT inputs.  The dependency expression references
``${my_var}``, and the generated dependency must resolve to the corresponding
parameterized producer spec.

The tests avoid invoking Canary through the CLI.  They generate temporary VVT
and PYT files, collect them through ``Workspace.collect``, and assert that the
resolved dependency of ``abc_post.my_var=0.1`` points to
``abc_run.my_var=0.1``.
"""

from pathlib import Path

import pytest

import _canary.config
from _canary.workspace import Workspace


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.delenv("CANARYCFG64", raising=False)
    monkeypatch.delenv("CANARYCFGFILE", raising=False)
    monkeypatch.setenv("CANARY_DISABLE_KB", "1")
    monkeypatch.chdir(tmp_path)

    with _canary.config.override():
        for plugin in ("canary_vvtest", "canary_pyt"):
            try:
                _canary.config.pluginmanager.ensure_loaded(plugin)
            except Exception:
                pass
        yield


def collect_specs(workspace_root: Path, file: Path):
    workspace = Workspace.create(workspace_root)
    file = file.absolute()
    specs = workspace.collect({str(file.parent): [file.name]})
    return [spec for spec in specs if not spec.mask]


def test_issue_89_vvt(tmp_path):
    demo = """
# VVT: parameterize (testname="abc_run or abc_post", autotype) : my_var = .1
#
# VVT: name : abc_run
#
# VVT: name : abc_post
# VVT: depends on (testname="abc_post") : abc_run.my_var=${my_var}
#
if __name__ == '__main__':
    print("Hello world")
"""
    f = tmp_path / "demo.vvt"
    f.write_text(demo)

    specs = collect_specs(tmp_path, f)

    assert {spec.name for spec in specs} == {"abc_run.my_var=.1", "abc_post.my_var=.1"}

    by_name = {spec.name: spec for spec in specs}
    post = by_name["abc_post.my_var=.1"]

    assert len(post.dependencies) == 1
    assert post.dependencies[0].spec.name == "abc_run.my_var=.1"


def test_issue_89_pyt(tmp_path):
    demo = """
import canary
canary.directives.parameterize('my_var', (0.1,), when={'testname': 'abc_run or abc_post'})
canary.directives.name('abc_run')
canary.directives.name('abc_post')
canary.directives.depends_on('abc_run.my_var=${my_var}', when={'testname': 'abc_post'})
#
if __name__ == '__main__':
    print("Hello world")
"""
    f = tmp_path / "demo.pyt"
    f.write_text(demo)

    specs = collect_specs(tmp_path, f)

    assert {spec.name for spec in specs} == {"abc_run.my_var=0.1", "abc_post.my_var=0.1"}

    by_name = {spec.name: spec for spec in specs}
    post = by_name["abc_post.my_var=0.1"]

    assert len(post.dependencies) == 1
    assert post.dependencies[0].spec.name == "abc_run.my_var=0.1"
