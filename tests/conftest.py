import pytest

from _nvtest.config import Config


@pytest.fixture(scope="function", autouse=False)
def config():
    def _config(args, dir):
        ip = Config.InvocationParams(args=args, dir=dir)
        return Config(invocation_params=ip)
    return _config
