def test_command_run_split_option():
    import _nvtest.command.run as rc

    a = "--acount=BAZ,--hosts='a,b,c',-S,FOO"
    parts = rc.SchedulerOptions.split_on_comma(a)
    expected = ["--acount=BAZ", "--hosts='a,b,c'", "-S", "FOO"]
    print(parts)
    print(expected)
    assert parts == expected
