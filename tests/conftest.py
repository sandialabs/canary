import os

import _nvtest.config
import pytest


@pytest.fixture(scope="function", autouse=True)
def config():
    os.environ["NVTEST_DISABLE_KB"] = "1"
    _nvtest.config.config = _nvtest.config.Config()
