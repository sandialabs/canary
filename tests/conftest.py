import os

import pytest

import _nvtest.config


@pytest.fixture(scope="function", autouse=True)
def config():
    os.environ["NVTEST_DISABLE_KB"] = "1"
    _nvtest.config._config = _nvtest.config.config.Config.factory()
