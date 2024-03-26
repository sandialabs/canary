def test_command_run_split_option():
    import _nvtest.command.run as rc

    a = "--acount=BAZ,--hosts='a,b,c',-S,FOO"
    parts = rc.SchedulerOptions.split_on_comma(a)
    expected = ["--acount=BAZ", "--hosts='a,b,c'", "-S", "FOO"]
    assert parts == expected
    a = ',--partition="short,batch"'
    parts = rc.SchedulerOptions.split_on_comma(a)
    expected = ['--partition="short,batch"']
    assert parts == expected
