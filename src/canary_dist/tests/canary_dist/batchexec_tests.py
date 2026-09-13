# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for canary_dist.batchexec — pure/isolated logic only."""

import os

import pytest

from canary_dist.batchexec import HPCConnectDistRunner


# ---------------------------------------------------------------------------
# filtered_env
# ---------------------------------------------------------------------------


def test_filtered_env_excludes_underscore_prefix(monkeypatch):
    monkeypatch.setenv("_PRIVATE_VAR", "secret")
    monkeypatch.setenv("NORMAL_VAR", "visible")
    env = dict(HPCConnectDistRunner.filtered_env())
    assert "_PRIVATE_VAR" not in env
    assert "NORMAL_VAR" in env


def test_filtered_env_excludes_bash_func(monkeypatch):
    monkeypatch.setenv("BASH_FUNC_myfunc%%", "() { echo hi; }")
    env = dict(HPCConnectDistRunner.filtered_env())
    assert not any(k.startswith("BASH_FUNC_") for k in env)


def test_filtered_env_excludes_user_home_ps1(monkeypatch):
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setenv("HOME", "/home/tester")
    monkeypatch.setenv("PS1", "$ ")
    env = dict(HPCConnectDistRunner.filtered_env())
    assert "USER" not in env
    assert "HOME" not in env
    assert "PS1" not in env


def test_filtered_env_includes_path(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = dict(HPCConnectDistRunner.filtered_env())
    assert "PATH" in env


def test_filtered_env_returns_all_non_filtered(monkeypatch):
    # Purge env and set exactly known vars
    for k in list(os.environ.keys()):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GOOD_VAR", "yes")
    monkeypatch.setenv("_BAD_VAR", "no")
    env = dict(HPCConnectDistRunner.filtered_env())
    assert env == {"GOOD_VAR": "yes"}


def test_filtered_env_is_generator():
    import types
    result = HPCConnectDistRunner.filtered_env()
    assert isinstance(result, types.GeneratorType)
