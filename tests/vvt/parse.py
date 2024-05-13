import nvtest.plugins.nvtest_vvt as vvtest
from _nvtest.enums import list_parameter_space


def test_parse_parameterize():
    s = """\
#!/usr/bin/env python3
# VVT: parameterize : np,n = 1,2 3,4 5,6
# VVT: : 7,8
"""
    commands, _ = vvtest.p_VVT(s)
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
    commands, _ = vvtest.p_VVT(s)
    assert commands[0].command == "parameterize"
    assert "%".join(commands[0].argument.split()) == "np,n%=%1,2%3,4%5,6"
    assert commands[0].options == {"autotype": True}
