# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

import _canary.plugins.builtin.vvtest as vvtest
import canary
from _canary.enums import list_parameter_space


def test_include_file(tmpdir):
    s = """\
#!/usr/bin/env python3
# VVT: include : ./file1.txt
"""
    with canary.filesystem.working_dir(tmpdir.strpath, create=True):
        with open("file1.txt", "w") as fh:
            fh.write("# VVT: include : ./file2.txt\n")
        with open("file2.txt", "w") as fh:
            fh.write("# VVT: include : ./file3.txt\n")
        with open("file3.txt", "w") as fh:
            fh.write("# VVT: parameterize (int, int) : np,n = 1,2 3,4 5,6 7,8\n")
        commands = list(vvtest.p_VVT(s))
        assert commands[0].command == "parameterize"
        assert "%".join(commands[0].argument.split()) == "np,n%=%1,2%3,4%5,6%7,8"
        names, values, kwds, _ = vvtest.p_PARAMETERIZE(commands[0])
        assert names == ["np", "n"]
        assert values == [[1, 2], [3, 4], [5, 6], [7, 8]]
        assert kwds == {"type": list_parameter_space}


def test_include_file_platform_no(tmpdir):
    s = """\
#!/usr/bin/env python3
# VVT: include (platform="incredible_os") : ./file1.txt
"""
    with canary.filesystem.working_dir(tmpdir.strpath, create=True):
        with open("file1.txt", "w") as fh:
            fh.write("# VVT: parameterize (int, int) : np,n = 1,2 3,4 5,6 7,8\n")
        commands = list(vvtest.p_VVT(s))
        assert len(commands) == 1
        assert commands[0].when == {"platforms": "incredible_os"}


def test_include_file_platform_yes(tmpdir):
    s = f"""\
#!/usr/bin/env python3
# VVT: include (platform="{sys.platform}") : ./file1.txt
"""
    with canary.filesystem.working_dir(tmpdir.strpath, create=True):
        with open("file1.txt", "w") as fh:
            fh.write("# VVT: parameterize (int, int) : np,n = 1,2 3,4 5,6 7,8\n")
        commands = list(vvtest.p_VVT(s))
        assert commands[0].command == "parameterize"
        assert "%".join(commands[0].argument.split()) == "np,n%=%1,2%3,4%5,6%7,8"
        names, values, kwds, _ = vvtest.p_PARAMETERIZE(commands[0])
        assert names == ["np", "n"]
        assert values == [[1, 2], [3, 4], [5, 6], [7, 8]]
        assert kwds == {"type": list_parameter_space}


def test_include_file_options_no(tmpdir):
    s = """\
#!/usr/bin/env python3
# VVT: include (option="baz") : ./file1.txt
"""
    with canary.filesystem.working_dir(tmpdir.strpath, create=True):
        with open("file1.txt", "w") as fh:
            fh.write("# VVT: parameterize (options=foo, int, int) : np,n = 1,2 3,4 5,6 7,8\n")
        commands = list(vvtest.p_VVT(s))
        assert len(commands) == 1
        assert commands[0].when == {"options": "foo and baz"}


def test_include_file_options_yes(tmpdir):
    s = """\
#!/usr/bin/env python3
# VVT: include (option="baz") : ./file1.txt
"""
    with canary.filesystem.working_dir(tmpdir.strpath, create=True), canary.config.override():
        with open("file1.txt", "w") as fh:
            fh.write("# VVT: parameterize (int,int) : np,n = 1,2 3,4 5,6 7,8\n")
        commands = list(vvtest.p_VVT(s))
        assert commands[0].command == "parameterize"
        assert commands[0].when == {"options": "baz"}
        canary.config.options.on_options = ["baz"]
        assert "%".join(commands[0].argument.split()) == "np,n%=%1,2%3,4%5,6%7,8"
        names, values, kwds, _ = vvtest.p_PARAMETERIZE(commands[0])
        assert names == ["np", "n"]
        assert values == [[1, 2], [3, 4], [5, 6], [7, 8]]
        assert kwds == {"type": list_parameter_space}
