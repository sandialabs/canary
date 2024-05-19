from nvtest.plugins.nvtest_ctest import parse_np


def test_parse_np():
    assert parse_np(["-n", "97"]) == 97
    assert parse_np(["-np", "23"]) == 23
    assert parse_np(["-c", "54"]) == 54
    assert parse_np(["--np", "82"]) == 82
    assert parse_np(["-n765"]) == 765
    assert parse_np(["-np512"]) == 512
    assert parse_np(["-c404"]) == 404
    assert parse_np(["--np=45"]) == 45
    assert parse_np(["--some-arg=4", "--other=foo"]) == 1
