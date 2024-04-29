import os


def test_command_describe(capsys):
    from _nvtest.main import NVTestCommand

    data_dir = os.path.join(os.path.dirname(__file__), "../data")
    describe = NVTestCommand("describe", debug=True)

    describe(os.path.join(data_dir, "empire.pyt"))
    captured = capsys.readouterr()
    assert describe.returncode == 0
    pyt_out = captured.out

    describe(os.path.join(data_dir, "empire.vvt"))
    captured = capsys.readouterr()
    assert describe.returncode == 0
    vvt_out = captured.out
