# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import pytest

import _canary.config
import _canary.util.multiprocessing as mp

mp.initialize()


@pytest.fixture(scope="function", autouse=True)
def config(request):
    try:
        env_copy = os.environ.copy()
        os.environ.pop("CONFIG_ENV_FILENAME", None)
        os.environ.pop("CANARYCFG64", None)
        os.environ["CANARY_DISABLE_KB"] = "1"
        # ``_canary.config`` serves attributes (get, set, getoption, ...) via a
        # module __getattr__ proxy that forwards to the live Config singleton.
        # Tests that monkeypatch these names leave real module attributes behind
        # (monkeypatch restores them as real attributes bound to a now-stale
        # Config), which would shadow the proxy for later tests.  Clear any such
        # leaked attributes before installing a fresh singleton.
        for name in ("get", "set", "getoption", "serialize", "pluginmanager"):
            _canary.config.__dict__.pop(name, None)
        _canary.config._config = _canary.config.config.Config()
        yield
    finally:
        os.environ.clear()
        os.environ.update(env_copy)
