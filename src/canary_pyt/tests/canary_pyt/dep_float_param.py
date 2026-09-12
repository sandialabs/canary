# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for dependency-pattern substitution with floating-point parameter values.

Verifies that ``depends_on('producer.my_var=${my_var}')`` resolves correctly
when ``my_var`` is a float (e.g. ``0.1``).  Previously, float parameter values
were formatted in ways that caused the pattern match to fail.
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
        _canary.config.pluginmanager.ensure_loaded("canary_pyt")
        yield


def collect_specs(workspace_root: Path, file: Path):
    workspace = Workspace.create(workspace_root)
    file = file.absolute()
    specs = workspace.collect({str(file.parent): [file.name]})
    return [spec for spec in specs if not spec.mask]


def test_pyt_dep_float_param_substitution_resolves(tmp_path):
    """${my_var} in a depends_on pattern resolves to the float-valued producer spec."""
    demo = """
import canary_pyt
canary_pyt.directives.parameterize('my_var', (0.1,), when={'testname': 'abc_run or abc_post'})
canary_pyt.directives.name('abc_run')
canary_pyt.directives.name('abc_post')
canary_pyt.directives.depends_on('abc_run.my_var=${my_var}', when={'testname': 'abc_post'})
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
