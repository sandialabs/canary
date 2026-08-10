# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Regression test for issue 62.

This test verifies PYT directive evaluation when ``enable`` and ``keywords`` are
conditioned on parameter values.  It intentionally works directly with the PYT
loader/model/adapter/emitter classes rather than running Canary through the CLI.

The covered behavior is that all parameterized specs are generated, but the
spec whose parameter value disables the test is masked, leaving only the
expected runnable specs.
"""

from pathlib import Path

import pytest

import _canary.config
import canary
import canary_pyt.pyt as pyt

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


def test_issue_62():
    with canary.filesystem.working_dir(HERE):
        m = pyt.PYTModel(".", "issue-62.pyt")
        calls = pyt.PYTLoader(file=m.file).parse()
        pyt.PYTAdapter(m).apply(calls)

        specs = pyt.PYTLockEmitter().lock(m, on_options=[])

    assert len(specs) == 3
    assert len([spec for spec in specs if not spec.mask]) == 2

    by_name = {spec.name: spec for spec in specs}
    assert not by_name["issue-62.Letter=a"].mask
    assert not by_name["issue-62.Letter=b"].mask
    assert by_name["issue-62.Letter=c"].mask
