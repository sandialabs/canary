import sys
import nvtest
import _nvtest.plugins.nvtest_vvt.generator as vvtest
from _nvtest.enums import list_parameter_space


def test_include_file(tmpdir):
    s = """\
#!/usr/bin/env python3
# VVT: include : ./file1.txt
"""
    with nvtest.filesystem.working_dir(tmpdir.strpath, create=True):
        with open("file1.txt", "w") as fh:
            fh.write("# VVT: include : ./file2.txt\n")
        with open("file2.txt", "w") as fh:
            fh.write("# VVT: include : ./file3.txt\n")
        with open("file3.txt", "w") as fh:
            fh.write("# VVT: parameterize : np,n = 1,2 3,4 5,6 7,8\n")
        commands = list(vvtest.p_VVT(s))
        assert commands[0].command == "parameterize"
        assert "%".join(commands[0].argument.split()) == "np,n%=%1,2%3,4%5,6%7,8"
        names, values, kwds = vvtest.p_PARAMETERIZE(commands[0])
        assert names == ["np", "n"]
        assert values == [[1, 2], [3, 4], [5, 6], [7, 8]]
        assert kwds == {"type": list_parameter_space}


def test_include_file_platform_no(tmpdir):
    s = """\
#!/usr/bin/env python3
# VVT: include (platform="incredible_os") : ./file1.txt
"""
    with nvtest.filesystem.working_dir(tmpdir.strpath, create=True):
        with open("file1.txt", "w") as fh:
            fh.write("# VVT: parameterize : np,n = 1,2 3,4 5,6 7,8\n")
        commands = list(vvtest.p_VVT(s))
        assert len(commands) == 0


def test_include_file_platform_yes(tmpdir):
    s = f"""\
#!/usr/bin/env python3
# VVT: include (platform="{sys.platform}") : ./file1.txt
"""
    with nvtest.filesystem.working_dir(tmpdir.strpath, create=True):
        with open("file1.txt", "w") as fh:
            fh.write("# VVT: parameterize : np,n = 1,2 3,4 5,6 7,8\n")
        commands = list(vvtest.p_VVT(s))
        assert commands[0].command == "parameterize"
        assert "%".join(commands[0].argument.split()) == "np,n%=%1,2%3,4%5,6%7,8"
        names, values, kwds = vvtest.p_PARAMETERIZE(commands[0])
        assert names == ["np", "n"]
        assert values == [[1, 2], [3, 4], [5, 6], [7, 8]]
        assert kwds == {"type": list_parameter_space}


def test_include_file_options_no(tmpdir):
    s = """\
#!/usr/bin/env python3
# VVT: include (option="baz") : ./file1.txt
"""
    with nvtest.filesystem.working_dir(tmpdir.strpath, create=True):
        with open("file1.txt", "w") as fh:
            fh.write("# VVT: parameterize : np,n = 1,2 3,4 5,6 7,8\n")
        commands = list(vvtest.p_VVT(s))
        assert len(commands) == 0


def test_include_file_options_yes(tmpdir):
    s = """\
#!/usr/bin/env python3
# VVT: include (option="baz") : ./file1.txt
"""
    with nvtest.filesystem.working_dir(tmpdir.strpath, create=True):
        with open("file1.txt", "w") as fh:
            fh.write("# VVT: parameterize : np,n = 1,2 3,4 5,6 7,8\n")
        nvtest.config.set("option:on_options", ["baz"])
        commands = list(vvtest.p_VVT(s))
        nvtest.config.set("option:on_options", [])
        assert commands[0].command == "parameterize"
        assert "%".join(commands[0].argument.split()) == "np,n%=%1,2%3,4%5,6%7,8"
        names, values, kwds = vvtest.p_PARAMETERIZE(commands[0])
        assert names == ["np", "n"]
        assert values == [[1, 2], [3, 4], [5, 6], [7, 8]]
        assert kwds == {"type": list_parameter_space}
