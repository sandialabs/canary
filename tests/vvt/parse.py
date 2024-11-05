import _nvtest.plugins.nvtest_vvt.generator as vvtest
from _nvtest.enums import list_parameter_space


def test_parse_parameterize():
    s = """\
#!/usr/bin/env python3
# VVT: parameterize : np,n = 1,2 3,4 5,6
# VVT: : 7,8
"""
    commands = list(vvtest.p_VVT(s))
    assert commands[0].command == "parameterize"
    assert "%".join(commands[0].argument.split()) == "np,n%=%1,2%3,4%5,6%7,8"
    names, values, kwds = vvtest.p_PARAMETERIZE(commands[0])
    assert names == ["np", "n"]
    assert values == [[1, 2], [3, 4], [5, 6], [7, 8]]
    assert kwds == {"type": list_parameter_space}


def test_parse_autotype():
    s = """\
#!/usr/bin/env python3
# VVT: parameterize (autotype) : np,n = 1,2 3,4 5,6
"""
    commands = list(vvtest.p_VVT(s))
    assert commands[0].command == "parameterize"
    assert "%".join(commands[0].argument.split()) == "np,n%=%1,2%3,4%5,6"
    assert commands[0].options == {"autotype": True}


def test_parse_parameterize_1():
    s = """\
#!/usr/bin/env python3
# VVT: parameterize: np, mesh_factor = 1 , 1.0    1 , 0.5    1 , 0.25
"""
    args = list(vvtest.p_VVT(s))
    assert args[0].command == "parameterize"
    names, values, kwds = vvtest.p_PARAMETERIZE(args[0])
    assert names == ["np", "mesh_factor"]
    assert values == [[1, 1.0], [1, 0.5], [1, 0.25]]


def test_csplit():
    assert vvtest.csplit("1 , 1.0    1 , 0.5    1 , 0.25") == [[1, 1.0], [1, 0.5], [1, 0.25]]
    assert vvtest.csplit("1 , baz    1 , 'foo'    5.0 , 0.25") == [
        [1, "baz"],
        [1, "foo"],
        [5.0, 0.25],
    ]
    assert vvtest.csplit("spam , baz    \"eggs\" , 'foo'    wubble , 0.25") == [
        ["spam", "baz"],
        ["eggs", "foo"],
        ["wubble", 0.25],
    ]


def test_parse_copy_rename():
    s = """\
#!/usr/bin/env python3
# VVT: copy (rename) : foo, baz  spam   ,ham
"""
    commands = list(vvtest.p_VVT(s))
    assert commands[0].command == "copy"
    assert "rename" in commands[0].options
    file_pairs = vvtest.csplit(commands[0].argument)
    assert file_pairs == [["foo", "baz"], ["spam", "ham"]]


def test_parse_baseline():
    s = """\
#!/usr/bin/env python3
# VVT: baseline : foo, baz  spam   ,ham
"""
    commands = list(vvtest.p_VVT(s))
    assert commands[0].command == "baseline"
    file_pairs = vvtest.csplit(commands[0].argument)
    assert file_pairs == [["foo", "baz"], ["spam", "ham"]]
