import os

import pytest

import _canary.config


@pytest.fixture(scope="function", autouse=True)
def config():
    os.environ["CANARY_DISABLE_KB"] = "1"
    _canary.config._config = _canary.config.config.Config.factory()
