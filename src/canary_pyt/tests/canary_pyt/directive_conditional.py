# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for PYT enable/keywords directives conditioned on parameter values.

Verifies that a parameterized spec whose ``enable`` is conditioned on its
parameter value gets masked while the others remain runnable.
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
        _canary.config.pluginmanager.ensure_loaded("canary_pyt")
        yield


def test_enable_conditioned_on_parameter_masks_matching_variant():
    """enable(False, when='parameters="Letter=c"') masks only the Letter=c spec."""
    with canary.filesystem.working_dir(HERE):
        m = pyt.PYTModel(".", "directive_conditional.pyt")
        calls = pyt.PYTLoader(file=m.file).parse()
        pyt.PYTAdapter(m).apply(calls)
        specs = pyt.PYTLockEmitter().lock(m, on_options=[])

    assert len(specs) == 3
    assert len([spec for spec in specs if not spec.mask]) == 2

    by_name = {spec.name: spec for spec in specs}
    assert not by_name["directive_conditional.Letter=a"].mask
    assert not by_name["directive_conditional.Letter=b"].mask
    assert by_name["directive_conditional.Letter=c"].mask
