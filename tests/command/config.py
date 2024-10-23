from _nvtest.main import NVTestCommand


def test_config_show():
    config = NVTestCommand("config")
    config("show")
