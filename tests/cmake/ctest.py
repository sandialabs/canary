import os

import pytest

from _nvtest.plugins.generators.nvtest_ctest import CTestTestFile
from _nvtest.plugins.generators.nvtest_ctest import parse_np
from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import set_executable
from _nvtest.util.filesystem import touchp
from _nvtest.util.filesystem import which
from _nvtest.util.filesystem import working_dir


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
            fh.write(
                """\
add_test(test1 "script.sh" "some-exe")
set_tests_properties(test1 PROPERTIES  ENVIRONMENT "CTEST_NUM_RANKS=5;SPAM=BAZ" LABELS "foo;baz" PROCESSORS "5" RESOURCE_GROUPS "5,gpus:1" _BACKTRACE_TRIPLES "CMakeLists.txt;0;")
add_test(test2 "mpiexec" "-n" "4" "some-exe")
set_tests_properties(test2 PROPERTIES  ENVIRONMENT "CTEST_NUM_RANKS=5;EGGS=SPAM" LABELS "foo;spam" _BACKTRACE_TRIPLES "CMakeLists.txt;0;")
"""
            )
        file = CTestTestFile(os.getcwd(), "CTestTestfile.cmake")
        cases = file.lock()
        assert len(cases) == 2

        case = cases[0]
        assert case.cpus == 5
        assert case.gpus == 5
        assert "foo" in case.keywords
        assert "baz" in case.keywords
        assert case.launcher is None
        assert case.command == "script.sh"
        assert case.variables["CTEST_NUM_RANKS"] == "5"
        assert case.variables["SPAM"] == "BAZ"

        case = cases[1]
        assert case.launcher.endswith("mpiexec")
        assert case.command == "some-exe"
        assert case.cpus == 4
        assert "foo" in case.keywords
        assert "spam" in case.keywords
        assert case.variables["CTEST_NUM_RANKS"] == "5"
        assert case.variables["EGGS"] == "SPAM"


@pytest.mark.skipif(which("cmake") is None, reason="cmake not on PATH")
def test_parse_ctesttestfile_1(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("foo.c", "w") as fh:
            fh.write("int main() { return 0; }\n")
        with open("CMakeLists.txt", "w") as fh:
            fh.write("cmake_minimum_required(VERSION 3.1...3.28)\n")
            fh.write("project(Foo VERSION 1.0 LANGUAGES C)\n")
            fh.write("enable_testing()\n")
            fh.write("add_executable(foo foo.c)\n")
            fh.write("add_test(NAME foo COMMAND foo)\n")
            fh.write('set_tests_properties(foo PROPERTIES LABELS "foo;baz" PROCESSORS 4)\n')
        with working_dir("build", create=True):
            cmake = Executable("cmake")
            cmake("..")
            file = CTestTestFile(os.getcwd(), "CTestTestfile.cmake")
            cases = file.lock()
            assert len(cases) == 1
            case = cases[0]
            assert case.cpus == 4
            assert "foo" in case.keywords
            assert "baz" in case.keywords
