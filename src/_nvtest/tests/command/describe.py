import importlib.resources
import os


def test_command_describe(capsys):
    from _nvtest.main import NVTestCommand

    data_dir = str(importlib.resources.files("_nvtest").joinpath("tests/data"))
    describe = NVTestCommand("describe")

    describe(os.path.join(data_dir, "empire.pyt"))
    captured = capsys.readouterr()
    assert describe.returncode == 0
    pyt_out = captured.out

    describe(os.path.join(data_dir, "empire.vvt"))
    captured = capsys.readouterr()
    assert describe.returncode == 0
    vvt_out = captured.out
