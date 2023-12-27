import os


def test_describe(capsys):
    from _nvtest.main import NVTestCommand

    data_dir = os.path.join(os.path.dirname(__file__), "data")
    command = NVTestCommand("describe")

    assert command(os.path.join(data_dir, "empire.pyt")) == 0
    captured = capsys.readouterr()
    pyt_out = captured.out

    assert command(os.path.join(data_dir, "empire.vvt")) == 0
    captured = capsys.readouterr()
    vvt_out = captured.out
