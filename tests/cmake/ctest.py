import os

import pytest
from _nvtest.util.filesystem import set_executable
from _nvtest.util.filesystem import touchp
from _nvtest.util.filesystem import which
from _nvtest.util.filesystem import working_dir
from nvtest.plugins.nvtest_ctest import CTestTestFile
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


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        touchp("mpiexec")
        touchp("script.sh")
        touchp("some-exe")
        set_executable("script.sh")
        set_executable("some-exe")
        set_executable("mpiexec")
        with open("CTestTestfile.cmake", "w") as fh:
            fh.write("""\
add_test(test1 "script.sh" "some-exe")
set_tests_properties(test1 PROPERTIES  ENVIRONMENT "CTEST_NUM_RANKS=5;SPAM=BAZ" LABELS "foo;baz" PROCESSORS "5" RESOURCE_GROUPS "5,gpus:1" _BACKTRACE_TRIPLES "CMakeLists.txt;0;")
add_test(test2 "mpiexec" "-n" "4" "some-exe")
set_tests_properties(test2 PROPERTIES  ENVIRONMENT "CTEST_NUM_RANKS=5;EGGS=SPAM" LABELS "foo;spam" _BACKTRACE_TRIPLES "CMakeLists.txt;0;")
""")
        file = CTestTestFile(os.getcwd(), "CTestTestfile.cmake")
        cases = file.freeze()
        assert len(cases) == 2

        assert cases[0]._processors == 5
        assert "baz" in cases[0]._keywords
        assert "SPAM" in cases[0].variables

        assert cases[1].launcher.endswith("mpiexec")
        assert cases[1]._processors == 4
        assert "foo" in cases[1]._keywords
        assert "EGGS" in cases[1].variables
