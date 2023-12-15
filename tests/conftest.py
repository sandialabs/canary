import pytest

import _nvtest.config


@pytest.fixture(scope="function", autouse=True)
def config():
    _nvtest.config.config = _nvtest.config.Config()
